"""用户行程服务：结构化行程的增删查 + 行程天气提醒。

核心价值：结合「用户某天的行程安排」+「当天真实天气」，生成出行提醒与推荐。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.itinerary import Itinerary
from app.services.weather_service import fetch_weather


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
        rows = (await s.execute(stmt.order_by(Itinerary.date, Itinerary.start_time))).scalars().all()
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


def _parse_date_expression(text: str) -> str | None:
    """从自然语言中解析日期，返回 YYYY-MM-DD 或 None。

    支持：今天/明天/后天/大后天 + 具体 YYYY-MM-DD 或 M月D日。
    """
    today = date.today()

    # 相对日期
    if "大后天" in text:
        d = today + timedelta(days=3)
    elif "后天" in text:
        d = today + timedelta(days=2)
    elif "明天" in text or "明日" in text:
        d = today + timedelta(days=1)
    elif "今天" in text or "今日" in text:
        d = today
    else:
        # 具体日期：YYYY-MM-DD 或 M月D日
        m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        m = re.search(r"(\d{1,2})月(\d{1,2})日?", text)
        if m:
            try:
                d = date(today.year, int(m.group(1)), int(m.group(2)))
                # 若已过今年，推到明年
                if d < today:
                    d = date(today.year + 1, int(m.group(1)), int(m.group(2)))
                return d.isoformat()
            except ValueError:
                return None
        return None

    return d.isoformat()


async def itinerary_weather_reminder(user_id: int, query: str) -> str:
    """行程天气提醒核心：解析日期 -> 取行程 -> 查天气 -> 生成提醒文本。

    返回结构化文本，供 LLM 阅读后生成最终回答。
    """
    date_str = _parse_date_expression(query)
    if date_str is None:
        # 未指定日期：默认取"未来最近的行程"
        items = await get_itinerary_by_date(user_id)
        if not items:
            return "你还没有安排行程。可先添加行程，我会结合天气给你出行提醒。"
        # 取未来最近的日期
        today = date.today().isoformat()
        future = [it for it in items if it["date"] >= today]
        target = future or items
        date_str = target[0]["date"]
        items = [it for it in target if it["date"] == date_str]
        header = f"你最近的行程是 {date_str}："
    else:
        items = await get_itinerary_by_date(user_id, date_str)
        if not items:
            return f"你在 {date_str} 没有安排行程。"
        header = f"你在 {date_str} 的行程安排："

    # 查该日期天气（用默认城市广州；行程 location 暂不逐个解析城市）
    weather_text = ""
    try:
        bundle = await fetch_weather("广州")
        # 找到对应日期的预报
        for d in bundle.daily:
            if d.date == date_str:
                weather_text = (
                    f"{d.weather_desc}，气温 {d.temp_min}~{d.temp_max}°C"
                    + (f"，降水 {d.precipitation_sum}mm" if d.precipitation_sum else "")
                )
                break
        if not weather_text and bundle.daily:
            weather_text = "暂无该日精确预报，可参考近期天气趋势"
    except Exception as exc:  # noqa: BLE001
        weather_text = f"天气查询失败：{exc}"

    lines = [header]
    for it in items:
        line = f"- {it['start_time'] or '全天'} {it['title']}"
        if it["location"]:
            line += f" @{it['location']}"
        if it["activity"]:
            line += f"（{it['activity']}）"
        lines.append(line)

    lines.append(f"\n当天天气：{weather_text}")
    lines.append("\n请基于以上行程和天气，逐条给出出行提醒与推荐（如雨天提醒带伞、高温提醒防晒补水、户外活动是否建议改期等）。")
    return "\n".join(lines)