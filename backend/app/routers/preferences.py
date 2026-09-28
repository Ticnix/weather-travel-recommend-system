"""用户偏好接口（Day 55）：GET 读取、PUT 整体替换。

**为什么单独一个 router 而不是塞进 users.py**：偏好是独立的领域
（存储、注入、设置页自成一体），与注册/登录无关；
单独成文件也避免每次加功能都去动越来越大的 users.py。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.user_preference import UserPreferenceData
from app.services import user_preference

router = APIRouter(prefix="/api/v1/users", tags=["用户偏好"])


@router.get("/me/preferences", response_model=dict)
async def get_preferences(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """读取当前用户偏好；从未设置过返回全默认（前端表单直接可用）。"""
    data = await user_preference.get_data(db, current.id)
    return success(user_preference.with_defaults(data))


@router.put("/me/preferences", response_model=dict)
async def put_preferences(
    payload: UserPreferenceData,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """整体替换偏好（前端每次提交完整表单，见 schema 的说明）。"""
    data = await user_preference.upsert(db, current.id, payload.model_dump())
    return success(user_preference.with_defaults(data), message="偏好已保存")
