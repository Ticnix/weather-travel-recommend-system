"""用户偏好的出入参（Day 55）。

**PUT 的语义是「整体替换」而不是部分更新**：前端每次提交完整表单。
理由：偏好里主要是布尔项，部分更新无法表达「取消勾选」——
`None` 到底是"没设置"还是"取消了"，两种语义混在一起迟早出 bug。
"""

from pydantic import BaseModel, Field


class UserPreferenceData(BaseModel):
    """用户偏好。布尔项默认 False（未勾选），文本项默认空串。"""

    sun_sensitive: bool = Field(default=False, description="怕晒")
    cold_sensitive: bool = Field(default=False, description="怕冷")
    with_elderly: bool = Field(default=False, description="有老人同行")
    with_children: bool = Field(default=False, description="有小孩同行")
    with_pet: bool = Field(default=False, description="携带宠物")
    prefer_outdoor: bool = Field(default=False, description="偏爱户外")
    prefer_indoor: bool = Field(default=False, description="偏爱室内")
    prefer_photo: bool = Field(default=False, description="喜欢拍照")
    prefer_food: bool = Field(default=False, description="对美食感兴趣")
    budget_low: bool = Field(default=False, description="预算有限")
    commute: str = Field(default="", max_length=30, description="主要通勤方式")
    diet: str = Field(default="", max_length=30, description="忌口 / 饮食注意")
