"""通知相关 Schema。"""

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    """浏览器推送订阅的加密密钥对（由 pushManager.subscribe 生成）。"""

    p256dh: str = Field(..., min_length=1, max_length=255)
    auth: str = Field(..., min_length=1, max_length=255)


class SubscribeIn(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2000)
    keys: PushKeys
    user_agent: str | None = Field(None, max_length=255)


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2000)
