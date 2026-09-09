"""用户反馈相关 Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FeedbackBase(BaseModel):
    content: str = Field(..., min_length=1)
    contact: Optional[str] = None
    status: str = "pending"  # pending / processing / resolved / closed


class FeedbackCreate(BaseModel):
    content: str = Field(..., min_length=1)
    contact: Optional[str] = None


class FeedbackUpdate(BaseModel):
    content: Optional[str] = None
    contact: Optional[str] = None
    status: Optional[str] = None
    reply: Optional[str] = None


class FeedbackOut(FeedbackBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    reply: Optional[str] = None
    reply_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
