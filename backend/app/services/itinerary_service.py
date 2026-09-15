"""用户行程服务：结构化行程的增删查。

行程天气提醒逻辑已迁移到 skills/itinerary_reminder/ 标准 Skill。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.itinerary import Itinerary


async def add_itinerary(
    user_id: int,
    title: str,
    date_str: str,
    start_time: str | None = None,
    location: str | None = None,
    activity: str | None = None,
    note: str | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """新增一条行程。校验日期格式（YYYY-MM-DD）。"""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise ValueError("日期格式应为 YYYY-MM-DD")

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> Itinerary:
        item = Itinerary(
            user_id=user_id,
            title=title,
            date=date_str,
            start_time=start_time,
            location=location,
            activity=activity,
            note=note,
        )
        s.add(item)
        await s.commit()
        await s.refresh(item)
        return item

    if owns_db:
        async with session as s:
            item = await _run(s)
    else:
        item = await _run(session)

    return {
        "id": item.id,
        "title": item.title,
        "date": item.date,
        "start_time": item.start_time,
        "location": item.location,
        "activity": item.activity,
    }


async def get_itinerary_by_date(
    user_id: int,
    date_str: str | None = None,
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """查询用户某天的行程；date_str 为 None 时返回未来 7 天内全部行程。

    返回按 start_time 排序的结构化行程列表。
    """
    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> list[dict[str, Any]]:
        stmt = select(Itinerary).where(Itinerary.user_id == user_id)
        if date_str:
            stmt = stmt.where(Itinerary.date == date_str)
        rows = (
            (await s.execute(stmt.order_by(Itinerary.date, Itinerary.start_time))).scalars().all()
        )
        return [
            {
                "id": r.id,
                "title": r.title,
                "date": r.date,
                "start_time": r.start_time,
                "location": r.location,
                "activity": r.activity,
                "note": r.note,
            }
            for r in rows
        ]

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)


async def update_itinerary(
    user_id: int,
    item_id: int,
    fields: dict[str, Any],
    db: AsyncSession | None = None,
) -> dict[str, Any] | None:
    """更新用户某条行程（只更新传入字段）；行程不存在或不属于该用户时返回 None。"""
    if fields.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(fields["date"])):
        raise ValueError("日期格式应为 YYYY-MM-DD")

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> dict[str, Any] | None:
        item = await s.get(Itinerary, item_id)
        if item is None or item.user_id != user_id:
            return None
        for key, value in fields.items():
            setattr(item, key, value)
        await s.commit()
        await s.refresh(item)
        return {
            "id": item.id,
            "title": item.title,
            "date": item.date,
            "start_time": item.start_time,
            "location": item.location,
            "activity": item.activity,
            "note": item.note,
        }

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)


async def delete_itinerary(user_id: int, item_id: int, db: AsyncSession | None = None) -> int:
    """删除用户某条行程（按 id），返回删除条数。"""
    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> int:
        stmt = delete(Itinerary).where(Itinerary.user_id == user_id, Itinerary.id == item_id)
        result = await s.execute(stmt)
        await s.commit()
        return result.rowcount or 0

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)
