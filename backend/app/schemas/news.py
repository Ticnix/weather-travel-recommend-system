"""资讯 / 公告相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NewsBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    full_text: str | None = None  # 原文正文（采集抓取，详情页直接阅读）
    cover_url: str | None = None
    source_url: str | None = None  # 原文链接（详情页内嵌展示）
    category: str = "news"  # news / notice / alert
    author: str | None = None
    is_top: bool = False
    is_published: bool = False


class NewsCreate(NewsBase):
    pass


class NewsUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    full_text: str | None = None
    cover_url: str | None = None
    source_url: str | None = None
    category: str | None = None
    author: str | None = None
    is_top: bool | None = None
    is_published: bool | None = None


class NewsOut(NewsBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    view_count: int = 0
    created_at: datetime
    updated_at: datetime


class NewsListQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    category: str | None = None
    keyword: str | None = None
    published_only: bool = False
