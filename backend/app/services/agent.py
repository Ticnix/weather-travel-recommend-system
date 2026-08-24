"""LangGraph Agent：Day 8 意图识别 + Day 9 MCP 工具调用。

图结构（ReAct 式工具循环）：
    START -> classify_intent（意图识别）
                |
                v
            agent_node（LLM 决策：调用工具 or 直接回答）
                |
          +-----+-----+
          | 有 tool_call | 无 tool_call
          v             v
       tools（执行 MCP 工具）  END
          |
          +-- 回到 agent_node（带工具结果继续推理）

设计要点：
- 工具来自 MCP Server（app/services/mcp_client.py 动态加载），与 Agent 解耦
- classify_intent 先用 LLM 判断意图，weather/travel/outfit 类才绑定工具，
  other（闲聊）不绑定工具，直接对话，节省 token 与延迟
- 工具调用失败由 handle_tool_errors 兜底，不会中断整个流程
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.services.llm_client import get_llm
from app.services.mcp_client import get_mcp_tools

logger = logging.getLogger(__name__)

# 意图分类提示词
INTENT_SYSTEM_PROMPT = (
    "你是天气出行助手的意图识别模块。请判断用户输入属于哪一类，"
    "只输出以下标签之一：weather（天气查询）、outfit（穿搭推荐）、"
    "travel（出行/行程规划）、other（其他/闲聊）。不要输出任何解释。"
)

# 生成回答提示词（含工具结果时使用）
GENERATE_SYSTEM_PROMPT = (
    "你是「广州天气旅行助手」，一个专业的本地出行服务 AI。"
    "请基于提供的真实数据（工具返回结果）回答用户问题，给出实用建议。"
    "禁止编造数据，若数据不足则如实说明。用中文简洁友好回答，控制在 200 字以内。"
)

# 纯闲聊回答提示词（不调用工具）
CHAT_SYSTEM_PROMPT = (
    "你是「广州天气旅行助手」，一个友好的本地出行服务 AI。"
    "用中文简洁友好地回答用户问题，控制在 100 字以内。"
)

# 需要绑定工具的意图（这些意图下 LLM 可决定调用 MCP 工具）
TOOL_INTENTS = {"weather", "travel", "outfit"}


class AgentState(TypedDict):
    """会话状态。messages 用 add_messages 做累加合并。"""

    messages: Annotated[list, add_messages]
    intent: str
    answer: str
    error: str


async def _classify_intent(state: AgentState) -> dict:
    """意图识别节点：用 LLM 判断用户意图，写入 state.intent。"""
    llm = get_llm()
    user_text = state["messages"][-1].content
    resp = await llm.ainvoke(
        [
            ("system", INTENT_SYSTEM_PROMPT),
            ("human", user_text),
        ]
    )
    intent = (resp.content if isinstance(resp.content, str) else str(resp.content)).strip()
    for label in ("weather", "outfit", "travel", "other"):
        if label in intent.lower():
            intent = label
            break
    else:
        intent = "other"
    logger.info("识别意图: %s（用户：%s）", intent, user_text)
    return {"intent": intent}


async def _agent_node(state: AgentState) -> dict:
    """LLM 决策节点：绑定工具（按意图），让模型决定调用工具还是直接回答。"""
    llm = get_llm()
    intent = state.get("intent", "other")

    if intent in TOOL_INTENTS:
        # 绑定 MCP 工具，LLM 可自主决定调用哪些工具
        tools = await get_mcp_tools()
        llm_with_tools = llm.bind_tools(tools)
        system = GENERATE_SYSTEM_PROMPT
    else:
        # 闲聊意图：不绑定工具，直接对话
        llm_with_tools = llm
        system = CHAT_SYSTEM_PROMPT

    messages = state["messages"]
    resp = await llm_with_tools.ainvoke(
        [("system", system), *messages]
    )

    result: dict = {"messages": [resp]}
    # 若无工具调用，说明模型已给出最终答案
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
    """异常兜底节点：工具/LLM 调用失败时返回友好提示。"""
    logger.exception("Agent 执行失败: %s", state.get("error"))
    return {
        "answer": "抱歉，服务暂时不可用，请稍后重试。",
        "error": state.get("error", "unknown"),
    }


def _should_error(state: AgentState) -> str:
    """路由：有 error 则进入兜底，否则继续。"""
    return "error" if state.get("error") else "agent"


async def _build_graph():
    """构建 LangGraph 状态机（含 MCP 工具节点）。"""
    tools = await get_mcp_tools()  # 预加载工具，供 ToolNode 使用
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


async def chat(user_input: str) -> dict:
    """对外暴露的单轮对话入口。返回 {intent, answer}。"""
    initial: AgentState = {
        "messages": [HumanMessage(content=user_input)],
        "intent": "",
        "answer": "",
        "error": "",
    }
    try:
        ag = await _get_agent()
        result = await ag.ainvoke(initial)
        return {"intent": result.get("intent", ""), "answer": result.get("answer", "")}
    except Exception as exc:  # noqa: BLE001 统一兜底，避免接口 500
        logger.exception("对话异常: %s", exc)
        return {"intent": "other", "answer": "抱歉，AI 服务暂时不可用，请稍后重试。"}