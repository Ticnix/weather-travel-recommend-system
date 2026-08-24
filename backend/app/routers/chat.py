"""对话接口：单轮 AI 对话（Day 8 LangGraph Agent）。"""

from fastapi import APIRouter

from app.core.response import success
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import agent

router = APIRouter(prefix="/api/v1/chat", tags=["AI 对话"])


@router.post("", response_model=dict)
async def chat(body: ChatRequest) -> dict:
    """单轮对话：意图识别 -> LLM 生成 -> 返回 {intent, answer}。"""
    result = await agent.chat(body.message)
    return success(ChatResponse(**result).model_dump(), message="对话完成")
