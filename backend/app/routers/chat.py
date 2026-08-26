"""对话接口：单轮/多轮 AI 对话（LangGraph Agent + MCP 工具 + RAG + SSE 流式）。"""

import json
import uuid

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.deps import OptionalUser
from app.core.response import success
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import agent, chat_history_service

router = APIRouter(prefix="/api/v1/chat", tags=["AI 对话"])


@router.post("", response_model=dict)
async def chat(body: ChatRequest, current: OptionalUser = None) -> dict:
    """单轮/多轮对话：意图识别 -> LLM 决策 -> MCP 工具/RAG -> 生成回答。

    可选鉴权：携带 token 时会把 user_id 传入 Agent，支持检索用户私有知识库
    并持久化多轮上下文；未登录则以匿名身份对话（仅公共能力，不记忆历史）。
    """
    user_id = current.id if current else None
    conversation_id = body.conversation_id or uuid.uuid4().hex[:16]

    # 读取历史（仅登录用户），构造多轮上下文
    history = await chat_history_service.get_recent_history(user_id, conversation_id)

    result = await agent.chat(body.message, user_id=user_id, history=history)

    # 持久化本轮对话（登录用户）
    if user_id is not None:
        await chat_history_service.add_message(user_id, conversation_id, "user", body.message)
        await chat_history_service.add_message(user_id, conversation_id, "assistant", result["answer"])

    data = ChatResponse(**result).model_dump()
    data["conversation_id"] = conversation_id
    return success(data, message="对话完成")


@router.post("/stream")
async def chat_stream(body: ChatRequest, current: OptionalUser = None):
    """SSE 流式对话：逐 token 推送，打字机效果。

    事件格式：
      - data: {"type": "intent", "intent": "weather"}    # 意图
      - data: {"type": "token", "content": "广州今天"}   # token 片段（可多个）
      - data: {"type": "done"}                            # 结束

    携带 token 时同样支持多轮上下文与历史持久化。
    """
    user_id = current.id if current else None
    conversation_id = body.conversation_id or uuid.uuid4().hex[:16]
    history = await chat_history_service.get_recent_history(user_id, conversation_id)

    async def event_generator():
        full_answer = ""
        try:
            async for evt in agent.chat_stream(body.message, user_id=user_id, history=history):
                etype = evt.get("type")
                if etype == "token":
                    full_answer += evt.get("content", "")
                yield {"event": "message", "data": json.dumps(evt, ensure_ascii=False)}
        except Exception:  # noqa: BLE001
            yield {
                "event": "message",
                "data": json.dumps({"type": "token", "content": "抱歉，AI 服务暂时不可用，请稍后重试。"}, ensure_ascii=False),
            }
        finally:
            # 流式结束后持久化（登录用户）
            if user_id is not None and full_answer:
                await chat_history_service.add_message(user_id, conversation_id, "user", body.message)
                await chat_history_service.add_message(user_id, conversation_id, "assistant", full_answer)

    return EventSourceResponse(event_generator())
