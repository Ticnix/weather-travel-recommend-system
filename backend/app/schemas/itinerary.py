"""行程模块 Schema。"""

from pydantic import BaseModel, Field


class ItineraryCreate(BaseModel):
    """新增行程请求（结构化字段）。"""

    title: str = Field(..., min_length=1, max_length=255, description="行程标题，如「白云山爬山」")
    date: str = Field(..., description="日期 YYYY-MM-DD")
    start_time: str | None = Field(default=None, description="开始时间 HH:MM")
    location: str | None = Field(default=None, max_length=128, description="地点")
    activity: str | None = Field(
        default=None, max_length=64, description="活动类型，如爬山/夜游/逛街"
    )
    note: str | None = Field(default=None, description="备注")


class ItineraryUpdate(BaseModel):
    """更新行程请求（字段可选，只更新传入的部分）。"""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    date: str | None = Field(default=None, description="日期 YYYY-MM-DD")
    start_time: str | None = None
    location: str | None = Field(default=None, max_length=128)
    activity: str | None = Field(default=None, max_length=64)
    note: str | None = None


class PlanRequest(BaseModel):
    """AI 一键排行程请求。

    只收一句自然语言：城市、天数、偏好都由 `itinerary_planner` 解析，
    前端不需要（也不应该）自己先拆一遍——那样两边的解析规则迟早不一致。
    """

    query: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="自然语言需求，如「周末想去广州玩两天，喜欢美食和拍照」",
    )


class ItineraryBatchCreate(BaseModel):
    """批量新增行程（AI 排行程的「一键保存」用）。"""

    items: list[ItineraryCreate] = Field(
        ..., min_length=1, max_length=30, description="要写入的行程条目"
    )
