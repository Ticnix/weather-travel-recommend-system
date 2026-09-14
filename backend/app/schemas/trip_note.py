"""行程笔记 Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TripNoteBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="笔记标题")
    content: str = Field(default="", description="Markdown 正文")
    note_date: Optional[str] = Field(default=None, description="关联日期 YYYY-MM-DD（可空）")
    location: Optional[str] = Field(default=None, max_length=128, description="关联地点（可空）")


class TripNoteCreate(TripNoteBase):
    """新建笔记。"""


class TripNoteUpdate(BaseModel):
    """更新笔记（字段可选，只更新传入的部分）。"""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = None
    note_date: Optional[str] = None
    location: Optional[str] = None


class TripNoteOut(TripNoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class TripNoteImportText(BaseModel):
    """粘贴文本导入（标题可空，缺省时从正文推断）。"""

    title: Optional[str] = Field(default=None, max_length=255)
    content: str = Field(..., min_length=1, description="Markdown / 纯文本正文")
    note_date: Optional[str] = None
    location: Optional[str] = None
