"""LangGraph Agent：Day 8 基础状态机。

图结构：
    START -> classify_intent（意图识别）-> generate（LLM 生成）-> END

- AgentState：会话状态（messages / intent / answer / error）
- classify_intent：用 LLM 判断用户意图类别（天气/穿搭/行程/闲聊等）
- generate：结合意图调用 DeepSeek 生成回答
- 单轮对话即可跑通，后续 Day 9/10 会接入 MCP 工具与 RAG 检索节点
"""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.services.llm_client import get_llm

logger = logging.getLogger(__name__)

# 意图分类提示词：让模型输出单一标签，便于后续路由到不同工具/技能
INTENT_SYSTEM_PROMPT = (
    "你是天气出行助手的意图识别模块。请判断用户输入属于哪一类，"
    "只输出以下标签之一：weather（天气查询）、outfit（穿搭推荐）、"
    "travel（出行/行程规划）、other（其他/闲聊）。不要输出任何解释。"
)

GENERATE_SYSTEM_PROMPT = (
    "你是「广州天气旅行助手」，一个专业的本地出行服务 AI。"
    "请用中文简洁、友好地回答用户问题，给出实用建议。"
    "回答控制在 200 字以内，语气自然。"
)


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
    # 归一化：只要包含关键标签即视为命中，否则归为 other
    for label in ("weather", "outfit", "travel", "other"):
        if label in intent.lower():
            intent = label
            break
    else:
        intent = "other"
    logger.info("识别意图: %s（用户：%s）", intent, user_text)
    return {"intent": intent}


async def _generate(state: AgentState) -> dict:
    """LLM 生成节点：结合意图生成回答。"""
    llm = get_llm()
    user_text = state["messages"][-1].content
    resp = await llm.ainvoke(
        [
            ("system", GENERATE_SYSTEM_PROMPT),
            ("human", user_text),
        ]
    )
    answer = resp.content if isinstance(resp.content, str) else str(resp.content)
    return {"answer": answer, "messages": [AIMessage(content=answer)]}


async def _handle_error(state: AgentState) -> dict:
    """异常兜底节点：LLM 调用失败时返回友好提示。"""
    logger.exception("Agent 执行失败: %s", state.get("error"))
    return {
        "answer": "抱歉，AI 服务暂时不可用，请稍后重试。",
        "error": state.get("error", "unknown"),
    }


def _should_error(state: AgentState) -> str:
    """路由：有 error 则进入兜底，否则进入生成。"""
    return "error" if state.get("error") else "generate"


def build_agent():
    """构建 LangGraph 状态机。"""
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", _classify_intent)
    graph.add_node("generate", _generate)
    graph.add_node("handle_error", _handle_error)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _should_error,
        {"error": "handle_error", "generate": "generate"},
    )
    graph.add_edge("generate", END)
    graph.add_edge("handle_error", END)

    return graph.compile()


# 单例 agent
agent = build_agent()


async def chat(user_input: str) -> dict:
    """对外暴露的单轮对话入口。返回 {intent, answer}。"""
    initial: AgentState = {
        "messages": [HumanMessage(content=user_input)],
        "intent": "",
        "answer": "",
        "error": "",
    }
    try:
        result = await agent.ainvoke(initial)
        return {"intent": result.get("intent", ""), "answer": result.get("answer", "")}
    except Exception as exc:  # noqa: BLE001 统一兜底，避免接口 500
        logger.exception("对话异常: %s", exc)
        return {"intent": "other", "answer": "抱歉，AI 服务暂时不可用，请稍后重试。"}
