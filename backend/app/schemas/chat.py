"""对话模块 Schema。"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户输入")
    conversation_id: str | None = Field(
        default=None, max_length=64, description="会话 ID（多轮对话时传入，空则新会话）"
    )


class ChatResponse(BaseModel):
    intent: str = Field(..., description="识别出的意图标签")
    answer: str = Field(..., description="模型生成的回答")
