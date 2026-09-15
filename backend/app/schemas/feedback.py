"""用户反馈相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackBase(BaseModel):
    content: str = Field(..., min_length=1)
    contact: str | None = None
    status: str = "pending"  # pending / processing / resolved / closed


class FeedbackCreate(BaseModel):
    content: str = Field(..., min_length=1)
    contact: str | None = None


class FeedbackUpdate(BaseModel):
    content: str | None = None
    contact: str | None = None
    status: str | None = None
    reply: str | None = None


class FeedbackOut(FeedbackBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    reply: str | None = None
    reply_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
