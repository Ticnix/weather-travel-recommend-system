"""LangGraph Agent：Day 8 意图识别 + Day 9 MCP 工具 + Day 10 RAG 与降级。

图结构（ReAct 式工具循环）：
    START -> classify_intent（意图识别）
                |
                v
            agent_node（LLM 决策：调用工具 / 反问 / 直接回答）
                |
          +-----+-----+
          | 有 tool_call | 无 tool_call（含反问/直答）
          v             v
       tools（执行 MCP 工具）  END
          |
          +-- 回到 agent_node（带工具结果继续推理）

设计要点：
- 工具来自 MCP Server（app/services/mcp_client.py 动态加载），与 Agent 解耦；
  含天气 / 预报 / 资讯 / 知识库（RAG）四类工具
- classify_intent 判断意图，weather/travel/outfit/knowledge 类才绑定工具，
  other（闲聊）不绑定，节省 token 与延迟
- 完善 ReAct 决策：信息不足时反问用户、有数据时直接回答、需查询时调用工具
- 全链路降级：意图识别失败用关键词兜底，LLM 调用失败走 handle_error，
  工具失败由 handle_tool_errors 兜底，保证接口永不 500
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.services.llm_client import get_llm
from app.services.local_tools import get_local_tools
from app.services.mcp_client import get_mcp_tools
from app.services.user_context import reset_current_user_id, set_current_user_id

logger = logging.getLogger(__name__)

# 意图分类提示词
INTENT_SYSTEM_PROMPT = (
    "你是天气出行助手的意图识别模块。请判断用户输入属于哪一类，"
    "只输出以下标签之一：weather（天气查询）、outfit（穿搭推荐）、"
    "travel（出行/行程规划）、knowledge（知识问答，如景点/美食/交通攻略）、"
    "other（其他/闲聊）。不要输出任何解释。"
)

# 生成回答提示词（含工具结果时使用）—— 含 ReAct 决策规则
GENERATE_SYSTEM_PROMPT = (
    "你是「广州天气旅行助手」，一个专业的本地出行服务 AI。\n"
    "请遵循以下决策规则：\n"
    "1. 一个复合问题往往同时涉及多个方面（如\"明天去广州塔穿什么、怎么去\"同时涉及天气+穿搭+路线），"
    "此时必须逐一调用所有相关工具：先 get_weather 查天气，再 recommend_outfit 出穿搭，"
    "再 plan_travel_route 出路线，最后整合成完整回答，不要只答其中一部分。\n"
    "2. 若需要实时数据，优先调用对应工具：天气/预报用 get_weather/get_forecast，"
    "本地攻略知识用 search_knowledge，资讯用 search_news。\n"
    "3. 若问题涉及实时性/时效性信息且上述工具覆盖不到（如景区当天开放情况、"
    "最新活动、门票价格、时事新闻），则调用 web_search 联网搜索。\n"
    "4. 若问题涉及用户自己的内容（如\"我的行程计划\"\"我上次收藏的\"等个性化信息），"
    "则调用 search_my_plans 检索该用户的私有知识库。\n"
    "5. 若问题涉及用户某天的行程安排或需要结合天气给出提醒（如\"明天有什么安排\""
    "\"后天要注意什么\"\"行程当天天气\"），则调用 check_itinerary_weather。\n"
    "6. 若问题涉及从A地到B地的路线/交通方式（如\"从广州南站到广州塔怎么走\""
    "\"去白云山坐地铁还是打车\"），则调用 plan_travel_route 出行规划。"
    "若用户未给出出发地，先用默认出发地（广州中心城区）给出参考方案，"
    "同时礼貌询问实际出发地以便精化。\n"
    "7. 若问题涉及穿什么衣服/穿搭建议（如\"明天爬山穿什么\"\"下雨天逛街穿什么\""
    "\"我怕冷怎么穿\"），则调用 recommend_outfit 穿搭推荐，并把用户提到的"
    "场景（爬山/逛街等）和偏好（怕冷/正式等）作为参数传入。\n"
    "8. 若问题可直接回答，则直接简洁作答。\n"
    "9. 能回答的部分先回答，确实缺失的关键信息（如具体出发地）再单独反问，"
    "不要因为一个信息缺失就放弃整段回答。\n"
    "禁止编造数据，工具未返回的数据一律不得臆造；数据不足时如实说明。\n"
    "用中文简洁友好回答，控制合理篇幅，复合问题可分点作答。"
)

# 纯闲聊回答提示词（不调用工具）
CHAT_SYSTEM_PROMPT = (
    "你是「广州天气旅行助手」，一个友好的本地出行服务 AI。"
    "用中文简洁友好地回答用户问题，控制在 100 字以内。"
)

# 需要绑定工具的意图（这些意图下 LLM 可决定调用 MCP 工具）
TOOL_INTENTS = {"weather", "travel", "outfit", "knowledge"}

# 关键词兜底规则（意图识别 LLM 失败时使用）
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "weather": ("天气", "气温", "温度", "下雨", "晴天", "台风", "降水", "湿度", "预报"),
    "outfit": ("穿", "穿搭", "衣服", "着装", "打扮"),
    "travel": ("去", "行程", "路线", "出行", "旅游", "交通", "地铁", "高铁", "航班", "怎么走"),
    "knowledge": ("景点", "美食", "好吃", "好玩", "攻略", "推荐", "酒店", "住宿", "历史", "文化"),
}


class AgentState(TypedDict):
    """会话状态。messages 用 add_messages 做累加合并。"""

    messages: Annotated[list, add_messages]
    intent: str
    answer: str
    error: str


def _keyword_intent(text: str) -> str:
    """关键词规则兜底：LLM 意图识别失败时使用。"""
    for label, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return label
    return "other"


async def _classify_intent(state: AgentState) -> dict:
    """意图识别节点：优先 LLM，失败降级到关键词规则。"""
    user_text = state["messages"][-1].content
    llm = get_llm()
    try:
        resp = await llm.ainvoke(
            [
                ("system", INTENT_SYSTEM_PROMPT),
                ("human", user_text),
            ]
        )
        intent = (resp.content if isinstance(resp.content, str) else str(resp.content)).strip()
        for label in ("weather", "outfit", "travel", "knowledge", "other"):
            if label in intent.lower():
                intent = label
                break
        else:
            intent = "other"
    except Exception as exc:  # noqa: BLE001 LLM 失败降级到关键词
        logger.warning("意图识别 LLM 调用失败，降级到关键词规则: %s", exc)
        intent = _keyword_intent(user_text)
    logger.info("识别意图: %s（用户：%s）", intent, user_text)
    return {"intent": intent}


async def _get_all_tools() -> list:
    """合并 MCP 工具（无状态公共工具）+ 本地工具（有用户态私有工具）。"""
    mcp_tools = await get_mcp_tools()
    local_tools = get_local_tools()
    return [*mcp_tools, *local_tools]


async def _agent_node(state: AgentState) -> dict:
    """LLM 决策节点：绑定工具（按意图），让模型决定调用工具/反问/直答。"""
    llm = get_llm()
    intent = state.get("intent", "other")

    if intent in TOOL_INTENTS:
        tools = await _get_all_tools()
        llm_with_tools = llm.bind_tools(tools)
        system = GENERATE_SYSTEM_PROMPT
    else:
        llm_with_tools = llm
        system = CHAT_SYSTEM_PROMPT

    messages = state["messages"]
    try:
        resp = await llm_with_tools.ainvoke([("system", system), *messages])
    except Exception as exc:  # noqa: BLE001 LLM 失败交给 handle_error
        logger.exception("LLM 生成节点调用失败: %s", exc)
        return {"error": str(exc)}

    result: dict = {"messages": [resp]}
    if not getattr(resp, "tool_calls", None):
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        result["answer"] = content
    return result


def _should_continue(state: AgentState) -> str:
    """路由：最后一条消息若含 tool_calls 则执行工具，否则结束。"""
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


async def _handle_error(state: AgentState) -> dict:
    """异常兜底节点：LLM 调用失败时返回友好提示。"""
    logger.error("Agent 执行失败: %s", state.get("error"))
    return {
        "answer": "抱歉，AI 服务暂时不可用，请稍后重试。",
        "error": state.get("error", "unknown"),
    }


def _should_error(state: AgentState) -> str:
    """路由：有 error 则进入兜底，否则继续。"""
    return "error" if state.get("error") else "agent"


async def _build_graph():
    """构建 LangGraph 状态机（含 MCP 工具 + 本地工具节点）。"""
    tools = await _get_all_tools()  # 预加载全部工具，供 ToolNode 使用
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", _classify_intent)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("handle_error", _handle_error)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _should_error,
        {"error": "handle_error", "agent": "agent"},
    )
    # 核心工具循环：agent -> tools -> agent（直到无 tool_calls 才 END）
    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("handle_error", END)

    return graph.compile()


_agent_instance = None


async def _get_agent():
    """惰性单例：首次调用时构建（需先加载 MCP 工具）。"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = await _build_graph()
    return _agent_instance


def _build_initial_state(user_input: str, history: list[dict] | None = None) -> AgentState:
    """构造 Agent 初始状态。

    history 为历史消息列表（[{"role": "user"/"assistant", "content": ...}]），
    按时间正序传入，用于多轮上下文。空/None 时为单轮。
    """
    messages: list = []
    for msg in history or []:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "user":
            messages.append(HumanMessage(content=content))
    messages.append(HumanMessage(content=user_input))

    return {
        "messages": messages,
        "intent": "",
        "answer": "",
        "error": "",
    }


async def chat(
    user_input: str,
    user_id: int | None = None,
    history: list[dict] | None = None,
) -> dict:
    """对话入口（单轮/多轮）。返回 {intent, answer}。

    参数：
    - user_id：当前登录用户 ID（可选）。设置到 contextvar，供
      search_my_plans 等「用户私有」工具读取，实现多租户数据隔离。
    - history：历史消息列表，用于多轮上下文。
    """
    initial = _build_initial_state(user_input, history)
    token = set_current_user_id(user_id)
    try:
        ag = await _get_agent()
        result = await ag.ainvoke(initial)
        return {"intent": result.get("intent", ""), "answer": result.get("answer", "")}
    except Exception as exc:  # noqa: BLE001 统一兜底，避免接口 500
        logger.exception("对话异常: %s", exc)
        return {"intent": "other", "answer": "抱歉，AI 服务暂时不可用，请稍后重试。"}
    finally:
        reset_current_user_id(token)


async def chat_stream(
    user_input: str,
    user_id: int | None = None,
    history: list[dict] | None = None,
):
    """流式对话入口（SSE）。逐 token yield，最后 yield 最终意图。

    用 LangGraph 的 astream(stream_mode="messages") 获取增量消息，
    每个 AIMessageChunk 的 content 作为一段 token 推送。
    """
    initial = _build_initial_state(user_input, history)
    token = set_current_user_id(user_id)
    final_intent = "chat"
    try:
        ag = await _get_agent()
        # 先跑一次意图识别（轻量，单次 LLM 调用），拿到 intent
        intent_state = await _classify_intent(initial)
        final_intent = intent_state.get("intent", "chat")
        yield {"type": "intent", "intent": final_intent}
        # 再流式生成：逐 token 推送，仅输出「agent 生成节点」的文本增量，
        # 跳过 classify_intent 节点的输出（其内容是意图标签，不应作为答案推送）
        async for chunk in ag.astream(initial, stream_mode="messages"):
            msg_chunk = chunk[0] if isinstance(chunk, tuple) else chunk
            meta = chunk[1] if isinstance(chunk, tuple) else {}
            if meta.get("langgraph_node") != "agent":
                continue
            if isinstance(msg_chunk, AIMessageChunk):
                piece = msg_chunk.content
                if isinstance(piece, str) and piece:
                    yield {"type": "token", "content": piece}
    except Exception as exc:  # noqa: BLE001 统一兜底
        logger.exception("流式对话异常: %s", exc)
        yield {"type": "token", "content": "抱歉，AI 服务暂时不可用，请稍后重试。"}
        final_intent = "other"
    finally:
        reset_current_user_id(token)

    yield {"type": "done"}