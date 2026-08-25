"""行程模块 Schema。"""

from pydantic import BaseModel, Field


class ItineraryCreate(BaseModel):
    """新增行程请求（结构化字段）。"""

    title: str = Field(..., min_length=1, max_length=255, description="行程标题，如「白云山爬山」")
    date: str = Field(..., description="日期 YYYY-MM-DD")
    start_time: str | None = Field(default=None, description="开始时间 HH:MM")
    location: str | None = Field(default=None, max_length=128, description="地点")
    activity: str | None = Field(default=None, max_length=64, description="活动类型，如爬山/夜游/逛街")
    note: str | None = Field(default=None, description="备注")