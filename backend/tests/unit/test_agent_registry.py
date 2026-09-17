"""领域注册表与路由测试（Day 41）。

这里最重要的一组是**一致性测试**：注册表里的工具名必须与真实注册的工具
逐字相同。写错不会报任何错，只会让某个领域 Agent 手里没有工具、
于是凭记忆瞎答——那是最难发现的一类问题，必须用测试钉死。
"""

import ast
import pathlib

import pytest

from app.services import local_tools
from app.services.agent_registry import (
    DOMAIN_DEPENDS,
    DOMAIN_ORDER,
    DOMAINS,
    group_tools,
    route_domains,
    tools_for_domain,
)
from mcp_server import tools as mcp_business


def _mcp_tool_names() -> set[str]:
    """MCP Server 实际注册的工具名（解析 server.py 里的 @mcp.tool()）。

    一开始我图省事，直接用「tools.py 里的公开协程函数」当工具清单——
    结果把 `fetch_weather` 这种内部辅助函数也算成了工具，测试报出
    "有工具没登记"，查半天才发现是提取方式错了。
    **工具清单必须以注册处为准**（server.py 的装饰器），不是以实现模块为准。
    """
    server_file = pathlib.Path(mcp_business.__file__).with_name("server.py")
    tree = ast.parse(server_file.read_text(encoding="utf-8"))

    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            is_tool_call = (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "tool"
            )
            if is_tool_call:
                names.add(node.name)
    return names


def _local_tool_names() -> set[str]:
    return {tool.name for tool in local_tools.get_local_tools()}


def _all_real_tool_names() -> set[str]:
    return _mcp_tool_names() | _local_tool_names()


class TestRegistryConsistency:
    def test_每个领域引用的工具都真实存在(self):
        real = _all_real_tool_names()
        for key, domain in DOMAINS.items():
            unknown = [name for name in domain.tools if name not in real]
            assert not unknown, f"领域 {key} 引用了不存在的工具：{unknown}"

    def test_所有真实工具都被分配到了领域(self):
        """没有孤儿工具：新增工具却忘了登记，应该在这里失败。"""
        assigned = {name for domain in DOMAINS.values() for name in domain.tools}
        orphans = _all_real_tool_names() - assigned
        assert not orphans, f"这些工具没有归属任何领域：{sorted(orphans)}"

    def test_依赖关系指向已知领域(self):
        for key, deps in DOMAIN_DEPENDS.items():
            assert key in DOMAINS
            for dep in deps:
                assert dep in DOMAINS, f"{key} 依赖了不存在的领域 {dep}"

    def test_每个领域都有工具与提示词(self):
        for key, domain in DOMAINS.items():
            assert domain.tools, f"{key} 没有工具"
            assert domain.prompt, f"{key} 没有提示词"
            assert domain.keywords or domain.patterns, f"{key} 没有任何路由依据"

    def test_分组函数把工具放进对应领域(self):
        class FakeTool:
            def __init__(self, name: str) -> None:
                self.name = name

        tools = [FakeTool(name) for name in _all_real_tool_names()]
        grouped = group_tools(tools)

        assert grouped["_unassigned"] == []
        assert {t.name for t in grouped["weather"]} == {"get_weather", "get_forecast"}

    def test_分组函数不丢弃未登记的工具(self):
        """新工具没登记时要能被发现，而不是静默消失。"""

        class FakeTool:
            def __init__(self, name: str) -> None:
                self.name = name

        grouped = group_tools([FakeTool("brand_new_tool")])
        assert [t.name for t in grouped["_unassigned"]] == ["brand_new_tool"]

    def test_工具名称未被重复分配(self):
        seen: dict[str, str] = {}
        for key, domain in DOMAINS.items():
            for name in domain.tools:
                assert name not in seen, f"工具 {name} 同时属于 {seen[name]} 与 {key}"
                seen[name] = key


class TestRouteDomains:
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("明天天气怎么样", ["weather"]),
            ("广州有什么好吃的", ["knowledge"]),
            # 穿搭依赖天气：问穿什么时应把天气一起答，否则建议是悬空的
            ("明天爬山穿什么", ["weather", "outfit"]),
            ("从广州南站到广州塔怎么走", ["route"]),
            ("周末想去广州玩两天", ["itinerary"]),
            ("帮我排个三日游", ["itinerary"]),
            ("有什么新公告吗", ["knowledge"]),
        ],
    )
    def test_单领域路由(self, question, expected):
        assert route_domains(question) == expected

    def test_复合问题路由到多个领域(self):
        domains = route_domains("明天去广州塔穿什么、怎么走")
        assert domains == ["weather", "outfit", "route"]

    @pytest.mark.parametrize("question", ["你好呀", "你是谁", "谢谢"])
    def test_闲聊不路由到任何领域(self, question):
        # 返回空 → 走通用回答，不绑定任何工具（省 token 也省延迟）
        assert route_domains(question) == []

    def test_路由顺序稳定(self):
        """同一问题多次路由结果必须一致，否则并行分支顺序会飘。"""
        question = "明天去广州塔穿什么、怎么走"
        assert route_domains(question) == route_domains(question)

    def test_结果按注册顺序排列(self):
        domains = route_domains("去广州塔怎么走、穿什么、天气如何")
        assert domains == [key for key in DOMAIN_ORDER if key in domains]

    def test_未知领域工具查询返回空(self):
        assert tools_for_domain("not_a_domain") == ()
