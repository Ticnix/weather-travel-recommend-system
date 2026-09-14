"""用户反馈模块 CRUD。

提交反馈公开（可匿名）；查看/管理/改状态需鉴权。普通用户仅能看自己的反馈，
管理员可看全部并流转状态（Day 3 先做基础鉴权，细粒度权限后续完善）。
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, OptionalUser
from app.core.response import success
from app.db.session import get_db
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.feedback import FeedbackCreate, FeedbackOut, FeedbackUpdate

router = APIRouter(prefix="/api/v1/feedback", tags=["用户反馈"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreate,
    current: OptionalUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    fb = Feedback(content=payload.content, contact=payload.contact)
    if current is not None:
        fb.user_id = current.id
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return success(FeedbackOut.model_validate(fb).model_dump(), message="反馈提交成功")


@router.get("", response_model=dict)
async def list_feedback(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
) -> dict:
    # 普通用户只看自己的；管理员看全部
    stmt = select(Feedback, User.username).outerjoin(User, User.id == Feedback.user_id)
    conditions = []
    if current.role != "admin":
        conditions.append(Feedback.user_id == current.id)
    if status_filter:
        conditions.append(Feedback.status == status_filter)
    # count 基于 feedback 行
    total = await db.scalar(
        select(func.count()).select_from(Feedback).where(*conditions)
    ) or 0
    # ⚠️ 筛选条件必须同时作用于 rows：此前只用在 count 上，
    # 导致普通用户能查到他人反馈（隐私问题），且 total 与实际条数不符
    if conditions:
        stmt = stmt.where(*conditions)
    rows = await db.execute(
        stmt.order_by(Feedback.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = []
    for fb, uname in rows:
        d = FeedbackOut.model_validate(fb).model_dump()
        d["username"] = uname or None
        items.append(d)
    return success({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/{fb_id}", response_model=dict)
async def get_feedback(
    fb_id: int, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    fb = await db.get(Feedback, fb_id)
    if fb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    if current.role != "admin" and fb.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该反馈")
    return success(FeedbackOut.model_validate(fb).model_dump())


@router.put("/{fb_id}", response_model=dict)
async def update_feedback(
    fb_id: int, payload: FeedbackUpdate, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    fb = await db.get(Feedback, fb_id)
    if fb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    data = payload.model_dump(exclude_unset=True)
    # 只有管理员可回复/改状态
    if current.role != "admin" and ("reply" in data or "status" in data):
        raise HTTPException(status_code=403, detail="无权回复或修改状态")
    for field, value in data.items():
        setattr(fb, field, value)
    if "reply" in data and data["reply"]:
        fb.reply_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(fb)
    return success(FeedbackOut.model_validate(fb).model_dump(), message="更新成功")


@router.delete("/{fb_id}", response_model=dict)
async def delete_feedback(
    fb_id: int, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    fb = await db.get(Feedback, fb_id)
    if fb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    if current.role != "admin" and fb.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除该反馈")
    await db.delete(fb)
    await db.commit()
    return success(message="删除成功")
