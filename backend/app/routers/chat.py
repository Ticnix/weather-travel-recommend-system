"""对话接口：单轮 AI 对话（LangGraph Agent + MCP 工具 + RAG）。"""

from fastapi import APIRouter

from app.core.deps import OptionalUser
from app.core.response import success
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import agent

router = APIRouter(prefix="/api/v1/chat", tags=["AI 对话"])


@router.post("", response_model=dict)
async def chat(body: ChatRequest, current: OptionalUser = None) -> dict:
    """单轮对话：意图识别 -> LLM 决策 -> MCP 工具/RAG -> 生成回答。

    可选鉴权：携带 token 时会把 user_id 传入 Agent，支持检索用户私有知识库；
    未登录则以匿名身份对话（仅公共能力）。
    """
    user_id = current.id if current else None
    result = await agent.chat(body.message, user_id=user_id)
    return success(ChatResponse(**result).model_dump(), message="对话完成")