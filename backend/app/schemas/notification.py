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


class MorningReportIn(BaseModel):
    """每日早报偏好（免打扰粒度为小时：5~22 点之间）。"""

    enabled: bool
    hour: int = Field(7, ge=5, le=22)


class NotificationPrefsIn(BaseModel):
    """通知偏好（部分更新：只传想改的字段）。

    刻意做成「全部可选」而不是要求全量提交：
    前端的每个开关是独立保存的，全量提交会把另一个开关的值回滚成
    上一次读到的旧值——用户快速连点两个开关时就会丢设置。
    """

    morning_enabled: bool | None = None
    morning_hour: int | None = Field(None, ge=5, le=22)
    alert_enabled: bool | None = None
    itinerary_enabled: bool | None = None
