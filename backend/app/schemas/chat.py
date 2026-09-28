"""对话模块 Schema。"""

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    # message 允许为空：用户"只想把这个文件/图片给你看"时不该被逼着打字。
    # 但**不能文字和附件都空**——那种请求没有意义（见下面的校验）。
    # 没写字时由服务端补一句默认请求（routers/chat.py::_default_ask），
    # 否则模型会不知道要对附件做什么。
    message: str = Field(default="", max_length=2000, description="用户输入（仅发附件时可为空）")
    conversation_id: str | None = Field(
        default=None, max_length=64, description="会话 ID（多轮对话时传入，空则新会话）"
    )
    # 多模态附件（先调 /chat/attachments 拿到 id，再在这里引用）：
    # 图片交给视觉模型，语音已转写成文本、文件已抽成文本
    attachments: list[str] = Field(
        default_factory=list, max_length=5, description="附件 id 列表（最多 5 个）"
    )

    @model_validator(mode="after")
    def _need_text_or_attachment(self) -> "ChatRequest":
        """文字与附件至少有一个，否则直接给出可读的原因而不是让下游空转。"""
        if not self.message.strip() and not self.attachments:
            raise ValueError("请至少输入一句话，或先添加一个附件")
        return self


class ChatResponse(BaseModel):
    intent: str = Field(..., description="识别出的意图标签")
    answer: str = Field(..., description="模型生成的回答")
