"""行程接口：结构化行程的增删查（均需鉴权）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.itinerary import ItineraryCreate, ItineraryUpdate
from app.services import itinerary_service

router = APIRouter(prefix="/api/v1/itinerary", tags=["行程管理"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_itinerary(
    payload: ItineraryCreate,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """新增一条行程。"""
    try:
        item = await itinerary_service.add_itinerary(
            user_id=current.id,
            title=payload.title,
            date_str=payload.date,
            start_time=payload.start_time,
            location=payload.location,
            activity=payload.activity,
            note=payload.note,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success(item, message="行程已添加")


@router.get("", response_model=dict)
async def list_itinerary(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    date: str | None = None,
) -> dict:
    """查询本人行程（可按 date=YYYY-MM-DD 过滤）。"""
    items = await itinerary_service.get_itinerary_by_date(current.id, date, db=db)
    return success({"items": items, "total": len(items)})


@router.put("/{item_id}", response_model=dict)
async def update_itinerary(
    item_id: int,
    payload: ItineraryUpdate,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """修改本人某条行程（只更新传入字段）。"""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    try:
        item = await itinerary_service.update_itinerary(current.id, item_id, fields, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    return success(item, message="已更新")


@router.delete("/{item_id}", response_model=dict)
async def delete_itinerary(
    item_id: int,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """删除本人某条行程。"""
    deleted = await itinerary_service.delete_itinerary(current.id, item_id, db=db)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="行程不存在")
    return success({"deleted": deleted}, message="删除成功")