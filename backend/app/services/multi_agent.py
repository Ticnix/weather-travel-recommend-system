"""Supervisor 多智能体协作（Day 41）。

架构：

    START → supervisor（路由：命中哪些领域）
              ├─ 0 个领域 → general（通用回答，不绑工具）
              ├─ 1 个领域 → {domain} → END           ← 直通，不合成
              └─ ≥2 领域  → {domain A, domain B} 并行 → synthesize → END

三个设计判断：

1. **单域直通不合成**：只有一个领域命中时，领域 Agent 的回答本身就是最终答案。
   再走一次"汇总 LLM"只会让它复述一遍——多一次调用、多一份延迟，
   还多一次改写走样的机会。省掉这步是白赚的。

2. **多域并行扇出**：LangGraph 的条件边返回**列表**即并行执行多个节点；
   所有领域节点都连到 synthesize，LangGraph 会在它们全部完成后才执行它
   （fan-in 同步），所以"等齐再汇总"不必自己加锁。

3. **默认不启用**：`AGENT_MODE` 决定走单 Agent 还是多 Agent，默认仍是 single。
   新架构上线的第一步是"能一键回退"。

与 Day 40 同样的原则：**能纯函数化的都抽出来**。
路由（`route_domains`）与汇总决策（`should_synthesize`）都能脱离 LLM 单测，
LLM 只负责它真正擅长的部分（理解与表达）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.services.agent_metrics import agent_metrics
from app.services.agent_registry import DOMAINS, route_domains
from app.services.llm_client import ainvoke_json, get_llm
from app.services.local_tools import get_local_tools
from app.services.mcp_client import get_mcp_tools
from app.services.user_context import reset_current_user_id, set_current_user_id

logger = logging.getLogger(__name__)

# 工具分组缓存（见 load_domain_tools）
_tools_cache: dict[str, list] | None = None

# 汇总时的组织顺序：先说天气（影响一切），最后说攻略资讯
DOMAIN_ORDER_HINT = "天气 → 穿搭 → 路线 → 行程 → 攻略资讯"

# 所有领域 Agent 共用的底线规则
SHARED_RULES = (
    "\n\n通用规则：\n"
    "1. 数据必须来自工具返回，**禁止编造**；查不到就如实说查不到。\n"
    "2. 只回答你负责的那部分，其他方面不用展开（有专门的助手在并行处理）。\n"
    "3. 用中文，简洁直接，不要写开场套话。"
)

ROUTE_SYSTEM_PROMPT = (
    "你是出行助手的调度模块。请判断用户的问题需要哪些领域助手参与，可多选。"
    "领域只有这些：weather（天气）、outfit（穿搭）、route（出行路线）、"
    "itinerary（用户的行程安排 / 新排行程 / 上传的攻略）、"
    "knowledge（景点美食攻略与资讯）。"
    '只输出 JSON，形如 {"domains": ["weather", "outfit"]}；'
    "如果问题与出行完全无关（闲聊、自我介绍等），返回空数组。"
)

SYNTHESIZE_SYSTEM_PROMPT = (
    "你是出行助手的主笔，负责把几位领域助手的答复整合成**一份**连贯的回答。\n"
    "要求：\n"
    "1. 去掉重复内容（同一句天气信息可能被多个助手提到）\n"
    "2. 保留各自的关键结论与数字，不要丢信息、不要改数字\n"
    f"3. 按「{DOMAIN_ORDER_HINT}」的自然顺序组织\n"
    "4. 不要出现「某助手说」这类表述，直接给结论\n"
    "5. 不得编造任何未在下面出现的内容\n"
    "6. 用中文，分点或分段，控制合理篇幅"
)

GENERAL_SYSTEM_PROMPT = (
    "你是「广州天气旅行助手」，一个友好的本地出行服务 AI。"
    "用中文简洁友好地回答用户问题，控制在 100 字以内。"
)


class DomainChoice(BaseModel):
    """LLM 路由的输出结构。"""

    domains: list[str] = Field(default_factory=list, description="命中的领域 key，可为空数组")


@dataclass
class DomainRun:
    """一次领域 Agent 运行的结果与开销。"""

    answer: str = ""
    llm_calls: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tools_used: list[str] = field(default_factory=list)


def _merge_answers(left: dict | None, right: dict | None) -> dict:
    """并行领域节点写同一个字段，需要合并而不是覆盖。"""
    return {**(left or {}), **(right or {})}


def _merge_metrics(left: dict | None, right: dict | None) -> dict:
    """并行分支的开销要累加。"""
    out = dict(left or {})
    for key, value in (right or {}).items():
        if isinstance(value, list) and isinstance(out.get(key), list):
            out[key] = [*out[key], *value]
        elif isinstance(value, (int, float)) and isinstance(out.get(key), (int, float)):
            out[key] = out[key] + value
        else:
            out[key] = value
    return out


class MultiAgentState(TypedDict):
    """多智能体图的状态。"""

    question: str
    domains: list[str]
    # 各领域 Agent 的回答（并行写入 → 需要 reducer 合并）
    domain_answers: Annotated[dict[str, str], _merge_answers]
    metrics: Annotated[dict[str, Any], _merge_metrics]
    answer: str
    error: str


def should_synthesize(domains: list[str]) -> bool:
    """是否需要一个汇总节点（纯函数）。

    只有一个领域时不需要——领域 Agent 的回答就是答案，
    再汇总一次纯属多花一次 LLM 调用。
    """
    return len(domains) > 1


async def load_domain_tools() -> dict[str, list]:
    """加载全部工具并按领域分组（MCP 无状态工具 + 本地有用户态工具）。

    结果缓存：一次请求里多个领域节点会并发调用它，
    不缓存就是每次去拉起/查询一遍 MCP 工具清单（纯浪费）。
    """
    from app.services.agent_registry import group_tools

    global _tools_cache
    if _tools_cache is None:
        mcp_tools = await get_mcp_tools()
        _tools_cache = group_tools([*mcp_tools, *get_local_tools()])
    return _tools_cache


def _add_usage(run: DomainRun, message: Any) -> None:
    """把一个 LLM 响应的 token 用量累加进 run（拿不到就跳过）。"""
    usage = getattr(message, "usage_metadata", None) or {}
    run.prompt_tokens += int(usage.get("input_tokens", 0) or 0)
    run.completion_tokens += int(usage.get("output_tokens", 0) or 0)


async def _invoke_tool(tools: list, call: dict) -> str:
    """执行一个工具调用，失败返回可读错误（不抛异常）。"""
    name = call.get("name", "")
    tool = next((item for item in tools if getattr(item, "name", "") == name), None)
    if tool is None:
        return f"工具 {name} 不可用，请改用你手上的其他工具。"
    try:
        result = await tool.ainvoke(call.get("args") or {})
        return result if isinstance(result, str) else str(result)
    except Exception as exc:  # noqa: BLE001 单个工具失败不该让整个 Agent 崩
        logger.warning("领域工具执行失败 tool=%s: %s", name, exc)
        return f"工具 {name} 执行失败：{exc}"


async def run_domain_agent(key: str, question: str, tools: list, max_steps: int = 3) -> DomainRun:
    """跑一个领域 Agent 的 ReAct 循环（工具 → 再推理），返回结果与开销。

    max_steps 是**硬上限**：模型偶尔会反复调用同一个工具，
    没有上限就会一直烧 token 直到超时。
    """
    domain = DOMAINS[key]
    run = DomainRun()
    llm = get_llm()
    bound = llm.bind_tools(tools) if tools else llm

    messages: list = [
        SystemMessage(content=domain.prompt + SHARED_RULES),
        HumanMessage(content=question),
    ]

    for _ in range(max_steps + 1):
        resp = await bound.ainvoke(messages)
        run.llm_calls += 1
        _add_usage(run, resp)
        messages.append(resp)

        calls = getattr(resp, "tool_calls", None) or []
        if not calls:
            content = resp.content if isinstance(resp.content, str) else str(resp.content)
            run.answer = content.strip()
            return run

        for call in calls:
            run.tools_used.append(call.get("name", ""))
            output = await _invoke_tool(tools, call)
            run.tool_calls += 1
            messages.append(ToolMessage(content=output, tool_call_id=call.get("id", "")))

    # 用尽步数：拿最后一次的内容兜底，避免整段回答为空
    logger.warning("领域 Agent 达到步数上限 key=%s，强制结束", key)
    last = messages[-1]
    content = getattr(last, "content", "")
    text = (content if isinstance(content, str) else str(content)).strip()
    run.answer = text or "该部分查询超时，请稍后再试。"
    return run


async def _llm_route(question: str) -> list[str]:
    """关键词没命中时，交给 LLM 判断需要哪些领域（失败返回空）。

    返回值**必须过滤**：模型可能编出不存在的领域名，
    直接拿去查 DOMAINS 会 KeyError。
    """
    try:
        choice = await ainvoke_json(question, DomainChoice, system=ROUTE_SYSTEM_PROMPT)
        picked = [key for key in choice.domains if key in DOMAINS]
    except Exception as exc:  # noqa: BLE001 路由失败退化为通用回答，不影响可用性
        logger.warning("LLM 领域路由失败，退化为通用回答: %s", exc)
        return []
    if picked:
        logger.info("LLM 路由命中领域: %s（用户：%s）", picked, question)
    return picked


# ---------------------------------------------------------------------------
# 图节点
# ---------------------------------------------------------------------------


async def plan_domains(question: str) -> list[str]:
    """决定这次问题要跑哪些领域（关键词优先，没命中再问 LLM）。

    单独暴露出来是因为**流式入口需要提前知道领域**：
    只有一个领域时，直接转发那个领域 Agent 的 token；
    多个领域时要等汇总节点的 token，否则用户会先后看到
    "各领域的分段回答"和"汇总后的完整回答"，等于把内容看了两遍。
    """
    domains = route_domains(question)
    if not domains:
        domains = await _llm_route(question)
    return domains


async def _supervisor_node(state: MultiAgentState) -> dict:
    """调度节点：关键词优先（免费且确定），没命中再问一次 LLM。

    若调用方已算好领域（流式路径为了决定转发哪个节点会先算一次），
    直接用现成结果，避免重复一次 LLM 路由调用。
    """
    if state.get("domains"):
        return {"domains": state["domains"]}
    return {"domains": await plan_domains(state["question"])}


# 领域 → 旧意图标签（前端按旧词表展示 intent，映射回去以免破坏兼容）
_DOMAIN_TO_LEGACY = {
    "weather": "weather",
    "outfit": "outfit",
    "route": "travel",
    "itinerary": "travel",
    "knowledge": "knowledge",
}


def to_legacy_intent(domains: list[str]) -> str:
    """把领域列表映射回旧的 intent 标签（纯函数）。

    多领域时优先报 travel：复合问题里"怎么去/行程"通常是最主要的诉求，
    前端也习惯用 travel 展示出行类回答。没有领域则回 other（闲聊）。
    """
    if not domains:
        return "other"
    labels = [_DOMAIN_TO_LEGACY.get(key, "other") for key in domains]
    if "travel" in labels:
        return "travel"
    return labels[0]


def _route_from_supervisor(state: MultiAgentState) -> list[str]:
    """条件边：返回**节点名列表** → LangGraph 并行执行（扇出）。

    没有命中领域时走 general（闲聊 / 无需工具的问题）。
    """
    domains = state.get("domains") or []
    if not domains:
        return ["general"]
    return [f"domain_{key}" for key in domains]


def _after_domain(state: MultiAgentState) -> str:
    """领域节点执行完之后的路由：多域才需要汇总。"""
    return "synthesize" if should_synthesize(state.get("domains") or []) else END


def _usage_of(message: Any, llm_calls: int = 1) -> dict[str, Any]:
    """从 LLM 响应里取开销（拿不到 token 数就只记调用次数）。"""
    usage = getattr(message, "usage_metadata", None) or {}
    return {
        "llm_calls": llm_calls,
        "tool_calls": 0,
        "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
        "completion_tokens": int(usage.get("output_tokens", 0) or 0),
        "tools_used": [],
    }


def _make_domain_node(key: str):
    """生成一个领域节点：只绑自己那几个工具。"""

    async def _node(state: MultiAgentState) -> dict:
        tools = (await load_domain_tools()).get(key, [])
        try:
            run = await run_domain_agent(key, state["question"], tools)
        except Exception as exc:
            logger.exception("领域 Agent 执行失败 key=%s: %s", key, exc)
            return {
                "domain_answers": {key: f"（{DOMAINS[key].label}部分暂时查询失败）"},
                "metrics": {"llm_calls": 0, "tool_calls": 0, "tools_used": []},
            }
        return {
            "domain_answers": {key: run.answer},
            "metrics": {
                "llm_calls": run.llm_calls,
                "tool_calls": run.tool_calls,
                "prompt_tokens": run.prompt_tokens,
                "completion_tokens": run.completion_tokens,
                "tools_used": run.tools_used,
            },
        }

    return _node


async def _general_node(state: MultiAgentState) -> dict:
    """通用回答：不绑工具（闲聊类问题不需要工具，省 token 也省延迟）。"""
    llm = get_llm()
    resp = await llm.ainvoke([("system", GENERAL_SYSTEM_PROMPT), ("human", state["question"])])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return {"answer": content.strip(), "metrics": _usage_of(resp)}


def build_merge_prompt(question: str, answers: dict[str, str]) -> str:
    """把各领域答复拼成汇总提示词（纯函数，可测）。

    按「天气 → 穿搭 → 路线 → 行程 → 攻略」排序而不是字典序：
    天气影响其他一切，先说它，后面几条才有落点。
    """
    blocks = [
        f"【{DOMAINS[key].label}助手的答复】\n{answers[key]}" for key in DOMAINS if answers.get(key)
    ]
    body = "\n\n".join(blocks) if blocks else "（没有收到任何领域助手的答复）"
    return f"用户问题：{question}\n\n{body}"


def fallback_merge(answers: dict[str, str]) -> str:
    """汇总 LLM 失败时的兜底：按领域顺序直接拼接原文。

    **宁可读起来生硬，也不能丢信息或整体失败**——
    多域回答里每一块都是真实查到的结果，拼起来仍然可用。
    """
    parts = [answers[key] for key in DOMAINS if answers.get(key)]
    return "\n\n".join(parts) if parts else "抱歉，暂时没能查到相关信息。"


async def _synthesize_node(state: MultiAgentState) -> dict:
    """汇总节点：把多域答复整合成一份连贯回答。"""
    answers = state.get("domain_answers") or {}
    llm = get_llm()
    try:
        resp = await llm.ainvoke(
            [
                ("system", SYNTHESIZE_SYSTEM_PROMPT),
                ("human", build_merge_prompt(state["question"], answers)),
            ]
        )
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        answer = content.strip()
        if not answer:
            answer = fallback_merge(answers)
        return {"answer": answer, "metrics": _usage_of(resp)}
    except Exception as exc:  # noqa: BLE001 汇总失败退化为拼接，别让整次回答失败
        logger.warning("汇总节点失败，退化为拼接: %s", exc)
        return {"answer": fallback_merge(answers), "metrics": {"llm_calls": 1}}


def stream_source_node(domains: list[str]) -> str:
    """流式时只转发哪个节点的 token（纯函数）。

    - 1 个领域 → 该领域节点（它的输出就是最终答案）
    - ≥2 个领域 → 汇总节点（转发领域节点会让用户把内容看两遍）
    - 0 个领域 → 通用回答节点
    """
    if len(domains) == 1:
        return f"domain_{domains[0]}"
    if len(domains) > 1:
        return "synthesize"
    return "general"


async def chat_multi_stream(
    question: str, user_id: int | None = None, domains: list[str] | None = None
):
    """多智能体流式入口（SSE）。

    与单 Agent 的流式实现同一个约束：**只转发最终产出节点的 token**，
    否则会把中间过程（领域分段的草稿）也推给用户，
    用户会先后看到"分段回答"和"汇总回答"，等于内容看了两遍。

    token 用量按全部节点的 chunk 累加，统计到的仍是这次请求的真实成本。
    domains 可由调用方预先算好传入（上层已算过就别再算一遍——
    LLM 兜底路由那一次是有成本的）。
    """
    domains = domains if domains is not None else await plan_domains(question)
    source = stream_source_node(domains)

    initial: MultiAgentState = {
        "question": question,
        "domains": domains,
        "domain_answers": {},
        "metrics": {},
        "answer": "",
        "error": "",
    }
    token = set_current_user_id(user_id)
    started = time.perf_counter()
    prompt_tokens = completion_tokens = 0

    try:
        ag = await _get_graph()
        async for chunk in ag.astream(initial, stream_mode="messages"):
            msg_chunk = chunk[0] if isinstance(chunk, tuple) else chunk
            meta = chunk[1] if isinstance(chunk, tuple) else {}

            usage = getattr(msg_chunk, "usage_metadata", None) or {}
            prompt_tokens += int(usage.get("input_tokens", 0) or 0)
            completion_tokens += int(usage.get("output_tokens", 0) or 0)

            if meta.get("langgraph_node") != source:
                continue
            if isinstance(msg_chunk, AIMessageChunk):
                piece = msg_chunk.content
                if isinstance(piece, str) and piece:
                    yield {"type": "token", "content": piece}
    except Exception as exc:
        logger.exception("多智能体流式对话异常: %s", exc)
        yield {"type": "token", "content": "抱歉，AI 服务暂时不可用，请稍后重试。"}
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        agent_metrics.observe(
            "multi",
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            domains=domains,
        )
        logger.info("多智能体流式完成 domains=%s ms=%.0f", domains, duration_ms)
        reset_current_user_id(token)

    yield {"type": "done"}


# ---------------------------------------------------------------------------
# 图与对外入口
# ---------------------------------------------------------------------------

_graph = None


async def _build_graph():
    """构建 Supervisor 图。

    条件边传「可能的目标节点列表」是 LangGraph 的扇出写法：
    路由函数返回**列表**即并行执行多个节点，
    等它们全部完成后再走各自的下游（这里就是 fan-in 到汇总）。
    """
    graph = StateGraph(MultiAgentState)

    graph.add_node("supervisor", _supervisor_node)
    graph.add_node("general", _general_node)
    graph.add_node("synthesize", _synthesize_node)
    domain_nodes = [f"domain_{key}" for key in DOMAINS]
    for key in DOMAINS:
        graph.add_node(f"domain_{key}", _make_domain_node(key))

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", _route_from_supervisor, [*domain_nodes, "general"])
    for name in domain_nodes:
        # 每个领域节点都连到 synthesize：多域时它们全部结束后才执行汇总
        graph.add_conditional_edges(name, _after_domain, ["synthesize", END])
    graph.add_edge("general", END)
    graph.add_edge("synthesize", END)

    return graph.compile()


async def _get_graph():
    """惰性单例（与单 Agent 一致：首次调用才构建）。"""
    global _graph
    if _graph is None:
        _graph = await _build_graph()
    return _graph


def reset_cache() -> None:
    """清空图与工具缓存（测试用：避免用例之间互相影响）。"""
    global _graph, _tools_cache
    _graph = None
    _tools_cache = None


def summarize_metrics(
    metrics: dict[str, Any], domains: list[str], duration_ms: float, answer: str
) -> dict[str, Any]:
    """把图状态里的开销整理成对外结构（纯函数，可直接比较）。"""
    return {
        "domains": list(domains),
        "llm_calls": int(metrics.get("llm_calls", 0) or 0),
        "tool_calls": int(metrics.get("tool_calls", 0) or 0),
        "prompt_tokens": int(metrics.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(metrics.get("completion_tokens", 0) or 0),
        "tools_used": list(metrics.get("tools_used", []) or []),
        "duration_ms": round(duration_ms, 1),
        "answer_length": len(answer or ""),
    }


async def chat_multi(question: str, user_id: int | None = None) -> dict[str, Any]:
    """多智能体对话入口。返回 {answer, domains, metrics}。

    失败时返回友好提示而不是抛异常——与单 Agent 的兜底立场一致：
    对话接口永远不该 500。
    """
    initial: MultiAgentState = {
        "question": question,
        "domains": [],
        "domain_answers": {},
        "metrics": {},
        "answer": "",
        "error": "",
    }
    token = set_current_user_id(user_id)
    started = time.perf_counter()

    try:
        ag = await _get_graph()
        result = await ag.ainvoke(initial)
        answers = result.get("domain_answers") or {}
        answer = result.get("answer") or fallback_merge(answers)
        domains = list(result.get("domains") or [])
        stat = summarize_metrics(
            result.get("metrics") or {}, domains, (time.perf_counter() - started) * 1000, answer
        )
        agent_metrics.observe(
            "multi",
            duration_ms=stat["duration_ms"],
            llm_calls=stat["llm_calls"],
            tool_calls=stat["tool_calls"],
            prompt_tokens=stat["prompt_tokens"],
            completion_tokens=stat["completion_tokens"],
            domains=domains,
        )
        logger.info(
            "多智能体完成 domains=%s llm=%s tool=%s ms=%s",
            domains,
            stat["llm_calls"],
            stat["tool_calls"],
            stat["duration_ms"],
        )
        return {"answer": answer, "domains": domains, "metrics": stat}
    except Exception as exc:
        logger.exception("多智能体执行失败: %s", exc)
        agent_metrics.observe(
            "multi", duration_ms=(time.perf_counter() - started) * 1000, error=True
        )
        return {"answer": "抱歉，AI 服务暂时不可用，请稍后重试。", "domains": [], "metrics": {}}
    finally:
        reset_current_user_id(token)
