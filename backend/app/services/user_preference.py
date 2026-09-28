"""用户偏好的读写与「给模型看」的描述（Day 55）。

**`describe()` 为什么单独成函数**：计划里明确要求"读偏好 → 拼接"只此一处——
对话、穿搭、排程三处都要注入偏好，各写一遍必然漂移
（改了措辞忘了另一处，用户会看到前后矛盾的建议）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_preference import UserPreference
from app.schemas.user_preference import UserPreferenceData

logger = logging.getLogger(__name__)

_FLAG_TEXTS: list[tuple[str, str]] = [
    ("sun_sensitive", "怕晒：优先安排遮荫或室内时段，并提醒防晒"),
    ("cold_sensitive", "怕冷：降温时提醒添衣，优先室内安排"),
    ("with_elderly", "有老人同行：行程节奏放缓，避免高强度徒步与拥挤时段"),
    ("with_children", "有小孩同行：优先亲子友好的场所与时段"),
    ("with_pet", "携带宠物：只推荐允许宠物进入的场所"),
    ("prefer_outdoor", "偏爱户外活动"),
    ("prefer_indoor", "偏爱室内活动"),
    ("prefer_photo", "喜欢拍照，可以推荐适合出片的地点与时段"),
    ("prefer_food", "对美食感兴趣，可顺带推荐本地特色小吃"),
    ("budget_low", "预算有限：优先免费或低价的项目与交通方式"),
]


async def get_data(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """读取原始偏好；从未设置过返回空 dict（调用方决定要不要补默认值）。"""
    row = (
        await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    ).scalar_one_or_none()
    return dict(row.data) if row else {}


async def upsert(db: AsyncSession, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """整体覆盖偏好（调用方传完整表单）。"""
    row = (
        await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        db.add(UserPreference(user_id=user_id, data=data))
    else:
        row.data = data
    await db.commit()
    return data


def with_defaults(data: dict[str, Any] | None) -> dict[str, Any]:
    """补齐默认值：前端表单需要拿到**完整的键集合**才能渲染勾选框。"""
    merged = UserPreferenceData().model_dump()
    if data:
        merged.update({k: v for k, v in data.items() if k in merged})
    return merged


def describe(data: dict[str, Any] | None) -> str:
    """把偏好转成可注入提示词的中文块；**只描述已设置的项**。

    空偏好返回空串——注入一段"该用户没有偏好"只会浪费 token，
    还可能诱导模型输出"考虑到你的偏好…"这种没话找话。
    """
    if not data:
        return ""
    lines = [text for key, text in _FLAG_TEXTS if data.get(key)]
    if data.get("commute"):
        lines.append(f"主要通勤方式：{data['commute']}")
    if data.get("diet"):
        lines.append(f"饮食注意：{data['diet']}")
    if not lines:
        return ""
    return "\n".join(["【用户偏好】（以下内容回答时请遵循）", *lines])
