"""资讯 / 公告相关 Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NewsBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    full_text: Optional[str] = None  # 原文正文（采集抓取，详情页直接阅读）
    cover_url: Optional[str] = None
    source_url: Optional[str] = None  # 原文链接（详情页内嵌展示）
    category: str = "news"  # news / notice / alert
    author: Optional[str] = None
    is_top: bool = False
    is_published: bool = False


class NewsCreate(NewsBase):
    pass


class NewsUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    full_text: Optional[str] = None
    cover_url: Optional[str] = None
    source_url: Optional[str] = None
    category: Optional[str] = None
    author: Optional[str] = None
    is_top: Optional[bool] = None
    is_published: Optional[bool] = None


class NewsOut(NewsBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    view_count: int = 0
    created_at: datetime
    updated_at: datetime


class NewsListQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    category: Optional[str] = None
    keyword: Optional[str] = None
    published_only: bool = False
