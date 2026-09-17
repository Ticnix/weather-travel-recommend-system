"""Supervisor 多智能体测试（Day 41）。

**不调真实 LLM**：这里用「按节点分辨身份的假模型」驱动整张图，
验证的是**编排逻辑**——路由对不对、单域是否跳过汇总、
并行分支有没有串味、失败降级是否有效。

与 Day 40 同一个思路：LLM 输出的内容不需要断言（那是模型的事），
要断言的是"我们怎么组织这些调用"。
"""

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from app.services import multi_agent
from app.services.agent_metrics import AgentMetrics
from app.services.agent_registry import DOMAINS


class FakeTool:
    """假工具：可指定返回值或抛错。"""

    def __init__(
        self, name: str, result: str = "工具返回的数据", raises: str | None = None
    ) -> None:
        self.name = name
        self.result = result
        self.raises = raises
        self.calls: list[dict] = []

    async def ainvoke(self, args: dict) -> str:
        self.calls.append(args)
        if self.raises:
            raise RuntimeError(self.raises)
        return self.result


def _content_of(item: Any) -> str:
    """取消息内容：LangChain 的调用有两种写法——

    - 领域节点传的是 SystemMessage/HumanMessage 对象
    - 通用/汇总节点传的是 ("system", "...") / ("human", "...") 元组

    假模型得同时认这两种，否则会报 `'tuple' object has no attribute 'content'`
    （第一次就是这么挂的）。
    """
    if isinstance(item, str):
        return item
    if isinstance(item, tuple) and len(item) == 2:
        return str(item[1])
    content = getattr(item, "content", "")
    return content if isinstance(content, str) else str(content)


class FakeLLM:
    """按「绑定了哪些工具 / 系统提示词」判断自己是谁，返回对应内容。

    这么设计是为了让断言不依赖提示词原文：
    领域节点靠 `bind_tools` 传入的工具名识别，汇总与通用节点靠提示词特征识别。
    """

    def __init__(
        self,
        recorder: list[str],
        script: list[Any] | None = None,
        capture: dict | None = None,
        fail_domain: bool = False,
        fail_merge: bool = False,
    ) -> None:
        self.recorder = recorder
        self.script = list(script or [])
        self.capture = capture if capture is not None else {}
        self.fail_domain = fail_domain
        self.fail_merge = fail_merge
        self.tool_names: list[str] = []
        self.bound = False

    def bind_tools(self, tools: list) -> "FakeLLM":
        self.bound = True
        self.tool_names = [getattr(tool, "name", "") for tool in tools]
        self.recorder.append(f"bind:{','.join(self.tool_names)}")
        return self

    def _domain_key(self) -> str | None:
        """用绑定的工具名反查自己属于哪个领域。"""
        for key, domain in DOMAINS.items():
            if set(domain.tools) & set(self.tool_names):
                return key
        return None

    async def ainvoke(self, messages: list) -> AIMessage:
        system = _content_of(messages[0]) if messages else ""

        # 脚本优先：测试"工具循环"时要能精确控制每一轮返回什么
        if self.script:
            if self.bound:
                self.recorder.append(self._domain_key() or "domain:unknown")
            return self.script.pop(0)

        # 领域节点：用绑定的工具名反查是哪个领域
        if self.bound:
            if self.fail_domain:
                raise RuntimeError("模拟领域模型故障")
            key = self._domain_key()
            self.recorder.append(key or "domain:unknown")
            label = DOMAINS[key].label if key else "领域"
            return AIMessage(content=f"{label}回答")

        if "主笔" in system:
            self.recorder.append("synthesize")
            # 记下汇总节点实际收到的内容，用于断言"降级信息有没有传下去"。
            # 注意这里同样要用 _content_of：汇总节点传的是元组而不是消息对象
            self.capture["merge_prompt"] = _content_of(messages[-1])
            if self.fail_merge:
                raise RuntimeError("模拟汇总模型故障")
            return AIMessage(content="汇总后的回答")
        self.recorder.append("general")
        return AIMessage(content="通用回答")


def _patch_llm(
    monkeypatch,
    recorder: list[str],
    script: list[Any] | None = None,
    capture: dict | None = None,
    fail_domain: bool = False,
    fail_merge: bool = False,
) -> None:
    """让每个节点拿到独立的假模型实例（避免 bind_tools 状态互相污染）。"""

    def factory(provider: str | None = None, **kwargs: Any) -> FakeLLM:
        return FakeLLM(recorder, script, capture, fail_domain, fail_merge)

    monkeypatch.setattr(multi_agent, "get_llm", factory)


def _patch_tools(monkeypatch, tools_by_domain: dict[str, list] | None = None) -> None:
    """给每个领域装配对应的假工具。

    必须是**真的按领域给出工具名**：假模型靠 `bind_tools` 收到的名字
    反查自己是谁，给空列表它就认不出身份，整张图的行为也就测不准了。
    """

    async def loader() -> dict[str, list]:
        base: dict[str, list] = {
            key: [FakeTool(name) for name in domain.tools] for key, domain in DOMAINS.items()
        }
        base["_unassigned"] = []
        base.update(tools_by_domain or {})
        return base

    monkeypatch.setattr(multi_agent, "load_domain_tools", loader)


class TestRunDomainAgent:
    async def test_无需工具时直接回答(self, monkeypatch):
        # 传入工具是为了让假模型能识别自己的身份（靠 bind_tools 反查领域）；
        # 本轮脚本没有 tool_calls，走的仍是"不调工具直接答"的路径
        _patch_llm(monkeypatch, [])

        run = await multi_agent.run_domain_agent("weather", "明天天气", [FakeTool("get_weather")])

        assert run.answer == "天气回答"
        assert run.llm_calls == 1
        assert run.tool_calls == 0

    async def test_调用工具后回到模型再回答(self, monkeypatch):
        tool = FakeTool("get_weather", result="广州 30℃ 晴")
        script = [
            AIMessage(
                content="",
                tool_calls=[{"name": "get_weather", "args": {"city": "广州"}, "id": "c1"}],
            ),
            AIMessage(content="今天广州 30℃ 晴"),
        ]
        _patch_llm(monkeypatch, [], script)

        run = await multi_agent.run_domain_agent("weather", "明天天气", [tool])

        assert run.tool_calls == 1
        assert run.llm_calls == 2
        assert run.answer == "今天广州 30℃ 晴"
        assert run.tools_used == ["get_weather"]
        assert tool.calls == [{"city": "广州"}]

    async def test_工具报错不中断回答(self, monkeypatch):
        tool = FakeTool("get_weather", raises="上游超时")
        script = [
            AIMessage(content="", tool_calls=[{"name": "get_weather", "args": {}, "id": "c1"}]),
            AIMessage(content="暂时查不到天气"),
        ]
        _patch_llm(monkeypatch, [], script)

        run = await multi_agent.run_domain_agent("weather", "天气", [tool])

        assert run.answer == "暂时查不到天气"
        assert run.tool_calls == 1

    async def test_模型编造不存在的工具时给出提示(self, monkeypatch):
        script = [
            AIMessage(content="", tool_calls=[{"name": "make_up", "args": {}, "id": "c1"}]),
            AIMessage(content="换个说法"),
        ]
        _patch_llm(monkeypatch, [], script)

        run = await multi_agent.run_domain_agent("weather", "天气", [FakeTool("get_weather")])

        assert run.answer == "换个说法"

    async def test_反复调用工具时会被步数上限截断(self, monkeypatch):
        """没有硬上限的话，模型反复调工具会一直烧 token 直到超时。"""

        def always_tool(provider=None, **kw):
            class LoopLLM:
                def bind_tools(self, tools):
                    return self

                async def ainvoke(self, messages):
                    return AIMessage(
                        content="继续查",
                        tool_calls=[{"name": "get_weather", "args": {}, "id": "x"}],
                    )

            return LoopLLM()

        monkeypatch.setattr(multi_agent, "get_llm", always_tool)

        run = await multi_agent.run_domain_agent(
            "weather", "天气", [FakeTool("get_weather")], max_steps=2
        )

        assert run.llm_calls == 3  # max_steps + 1 次后强制结束
        assert run.answer  # 仍要有内容返回，不能是空


class TestChatMultiGraph:
    """整张图的编排行为（假模型驱动，验证的是编排而不是模型）。"""

    @pytest.fixture(autouse=True)
    def _fresh_graph(self):
        multi_agent.reset_cache()
        yield
        multi_agent.reset_cache()

    async def test_单领域直通不调用汇总(self, monkeypatch):
        recorder: list[str] = []
        _patch_llm(monkeypatch, recorder)
        _patch_tools(monkeypatch)

        result = await multi_agent.chat_multi("明天天气怎么样")

        assert result["domains"] == ["weather"]
        assert result["answer"] == "天气回答"
        # 关键：只有领域节点跑过，没有 synthesize——单域直通省掉一次 LLM 调用
        assert recorder == ["bind:get_weather,get_forecast", "weather"]
        assert result["metrics"]["llm_calls"] == 1

    async def test_复合问题并行执行多个领域再汇总(self, monkeypatch):
        recorder: list[str] = []
        _patch_llm(monkeypatch, recorder)
        _patch_tools(monkeypatch)

        result = await multi_agent.chat_multi("明天去广州塔穿什么、怎么走")

        assert result["domains"] == ["weather", "outfit", "route"]
        assert result["answer"] == "汇总后的回答"
        assert "synthesize" in recorder
        assert {"weather", "outfit", "route"} <= set(recorder)
        # 3 个领域各 1 次 + 汇总 1 次
        assert result["metrics"]["llm_calls"] == 4

    async def test_闲聊走通用回答且不绑工具(self, monkeypatch):
        recorder: list[str] = []
        _patch_llm(monkeypatch, recorder)
        _patch_tools(monkeypatch)

        result = await multi_agent.chat_multi("你好呀")

        assert result["domains"] == []
        assert result["answer"] == "通用回答"
        assert recorder == ["general"]

    async def test_每个领域只拿到自己的工具(self, monkeypatch):
        """这是多智能体的核心收益：工具候选从 10 个降到 1~3 个。"""
        recorder: list[str] = []
        _patch_llm(monkeypatch, recorder)
        _patch_tools(monkeypatch)

        await multi_agent.chat_multi("明天天气怎么样")
        await multi_agent.chat_multi("广州有什么好吃的")

        assert "bind:get_weather,get_forecast" in recorder
        assert "bind:search_knowledge,search_news,web_search" in recorder

    async def test_单个领域失败时降级不中断(self, monkeypatch):
        recorder: list[str] = []
        capture: dict = {}
        _patch_llm(monkeypatch, recorder, capture=capture, fail_domain=True)
        _patch_tools(monkeypatch)

        result = await multi_agent.chat_multi("明天去广州塔穿什么、怎么走")

        # 领域节点全部失败 → 走降级拼接，但整次回答仍然完成
        assert result["answer"]
        assert "暂时查询失败" in capture.get("merge_prompt", "")

    async def test_汇总失败时退化为拼接而不是报错(self, monkeypatch):
        recorder: list[str] = []
        _patch_llm(monkeypatch, recorder, fail_merge=True)
        _patch_tools(monkeypatch)

        result = await multi_agent.chat_multi("明天去广州塔穿什么、怎么走")

        # 拼接兜底按领域顺序把原文拼起来，信息不丢
        assert "天气回答" in result["answer"]
        assert "穿搭回答" in result["answer"]

    async def test_图构建失败时返回友好提示(self, monkeypatch):
        async def broken():
            raise RuntimeError("图构建失败")

        monkeypatch.setattr(multi_agent, "_get_graph", broken)

        result = await multi_agent.chat_multi("明天天气怎么样")

        assert result["domains"] == []
        assert "暂时不可用" in result["answer"]


class TestPureHelpers:
    """纯函数：这些是"能脱离 LLM 测"的部分，也是最该测的部分。"""

    def test_多域才需要汇总(self):
        assert multi_agent.should_synthesize([]) is False
        assert multi_agent.should_synthesize(["weather"]) is False
        assert multi_agent.should_synthesize(["weather", "outfit"]) is True

    def test_流式只转发最终产出节点(self):
        assert multi_agent.stream_source_node(["weather"]) == "domain_weather"
        assert multi_agent.stream_source_node(["weather", "outfit"]) == "synthesize"
        assert multi_agent.stream_source_node([]) == "general"

    def test_领域映射回旧意图标签(self):
        assert multi_agent.to_legacy_intent([]) == "other"
        assert multi_agent.to_legacy_intent(["weather"]) == "weather"
        # 路线与行程都归到旧的 travel 标签，避免前端词表失效
        assert multi_agent.to_legacy_intent(["route"]) == "travel"
        assert multi_agent.to_legacy_intent(["itinerary"]) == "travel"
        assert multi_agent.to_legacy_intent(["weather", "route"]) == "travel"

    def test_汇总提示按领域顺序组织(self):
        prompt = multi_agent.build_merge_prompt(
            "明天穿什么", {"outfit": "穿短袖", "weather": "晴 30℃"}
        )
        # 天气在前、穿搭在后：天气影响其他一切，先说它后面才有落点
        assert prompt.index("晴 30℃") < prompt.index("穿短袖")
        assert "明天穿什么" in prompt

    def test_汇总提示跳过空答复(self):
        prompt = multi_agent.build_merge_prompt("问题", {"weather": "晴", "outfit": ""})
        assert "晴" in prompt
        assert "穿搭" not in prompt

    def test_汇总提示在完全没答复时也给出占位(self):
        assert "没有收到" in multi_agent.build_merge_prompt("问题", {})

    def test_兜底拼接保留全部内容(self):
        text = multi_agent.fallback_merge({"weather": "晴", "outfit": "穿短袖"})
        assert "晴" in text and "穿短袖" in text

    def test_兜底拼接空输入不报错(self):
        assert multi_agent.fallback_merge({}) == "抱歉，暂时没能查到相关信息。"

    def test_开销汇总结构完整(self):
        stat = multi_agent.summarize_metrics(
            {"llm_calls": 3, "tool_calls": 2, "prompt_tokens": 100, "completion_tokens": 50},
            ["weather", "outfit"],
            1234.56,
            "回答" * 10,
        )
        assert stat["llm_calls"] == 3
        assert stat["tool_calls"] == 2
        assert stat["domains"] == ["weather", "outfit"]
        assert stat["duration_ms"] == 1234.6
        assert stat["answer_length"] == 20

    def test_开销汇总容忍缺失字段(self):
        stat = multi_agent.summarize_metrics({}, [], 0.0, "")
        assert stat["llm_calls"] == 0
        assert stat["tools_used"] == []


class TestAgentMetrics:
    def test_按模式分别聚合均值(self):
        m = AgentMetrics()
        m.observe("single", duration_ms=1000, llm_calls=2, tool_calls=1, prompt_tokens=100)
        m.observe("single", duration_ms=3000, llm_calls=4, tool_calls=3, prompt_tokens=300)
        m.observe("multi", duration_ms=2000, llm_calls=4, domains=["weather", "outfit"])

        snap = m.snapshot()["modes"]
        assert snap["single"]["runs"] == 2
        assert snap["single"]["avg_ms"] == 2000.0
        assert snap["single"]["avg_llm_calls"] == 3.0
        assert snap["single"]["total_tokens"] == 400

        assert snap["multi"]["runs"] == 1
        assert snap["multi"]["domain_hits"] == {"weather": 1, "outfit": 1}
        assert snap["multi"]["domain_counts"] == {"2": 1}

    def test_重置后回到空(self):
        m = AgentMetrics()
        m.observe("single", duration_ms=10)
        m.reset()
        assert m.snapshot()["modes"] == {}

    def test_记录错误次数(self):
        m = AgentMetrics()
        m.observe("multi", duration_ms=10, error=True)
        assert m.snapshot()["modes"]["multi"]["errors"] == 1
