"""行程导出为 .ics 日历文件（Day 53）。

**为什么导出未来而不是全部**：日历订阅的价值在「到点提醒」，
过去的行程放进去只会在翻日历时碍事。

**为什么时间用 UTC 而不是 TZID=Asia/Shanghai**：严格的 TZID 需要在组件里
带 VTIMEZONE 定义，缺了它部分客户端（尤其 iOS）会按设备本地时区硬解释，
"上午 9 点的行程"会变成"下午 5 点的提醒"。UTC 所有客户端都认。

**为什么 UID 里带行程 id**：同一行程重复导出时，日历客户端按 UID
去重/更新，而不是每次都多出一条重复事件。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.itinerary import Itinerary

logger = logging.getLogger(__name__)

CN_TZ = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")


def _escape(text: str) -> str:
    """RFC 5545 转义：反斜杠 / 分号 / 逗号 / 换行。

    地点名带逗号（如「长隆,南门」）不转义的话，
    日历客户端会把 LOCATION 截断在逗号处。"""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """按 **75 字节** 折行（RFC 5545 要求；中文一个字 3 字节，必须按字节算）。

    折行点必须在字符边界上，不能把一个多字节字符拆成两半。
    续行以一个空格开头（这个空格计入下一行的 75 字节）。"""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    while len(raw) > 75:
        cut = 75
        while cut > 0:
            try:
                parts.append(raw[:cut].decode("utf-8"))
                break
            except UnicodeDecodeError:
                cut -= 1
        raw = b" " + raw[cut:]
    parts.append(raw.decode("utf-8"))
    return "\r\n ".join(parts)


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


async def collect_future(
    user_id: int, db: AsyncSession, *, days: int = 365
) -> list[dict[str, Any]]:
    """未来 days 天的行程（含今天），按日期与开始时间排序。"""
    today = datetime.now(CN_TZ).date()
    horizon = today + timedelta(days=days)
    rows = (
        (
            await db.execute(
                select(Itinerary)
                .where(
                    Itinerary.user_id == user_id,
                    Itinerary.date >= today.isoformat(),
                    Itinerary.date <= horizon.isoformat(),
                )
                .order_by(Itinerary.date, Itinerary.start_time)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "title": r.title,
            "date": r.date,
            "start_time": r.start_time,
            "location": r.location,
            "activity": r.activity,
            "note": getattr(r, "note", None),
        }
        for r in rows
    ]


def build_ics(items: list[dict[str, Any]], now: datetime | None = None) -> str:
    """把行程列表拼成 VCALENDAR 文本。

    - 有开始时间 → 定长事件（默认 2 小时，日历里只是占位提醒）
    - 没有开始时间或时间格式不对 → 全天事件：用户只知道「那天有事」，
      服务端不该替他编一个具体时间
    """
    stamp = (now or datetime.now(CN_TZ)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//广州天气助手//行程导出//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:我的行程（广州天气助手）",
    ]
    for item in items:
        title = item["title"] + (f" · {item['activity']}" if item.get("activity") else "")
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:itinerary-{item['id']}@weather-assistant")
        lines.append(f"DTSTAMP:{stamp}")

        has_start = False
        if item.get("start_time"):
            try:
                start = datetime.strptime(
                    f"{item['date']} {item['start_time']}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=CN_TZ)
            except ValueError:
                start = None  # 时间不是 HH:MM（如手输的「9点」）：退回全天事件
            if start is not None:
                lines.append(f"DTSTART:{_utc(start)}")
                lines.append(f"DTEND:{_utc(start + timedelta(hours=2))}")
                has_start = True
        if not has_start:
            lines.append(f"DTSTART;VALUE=DATE:{item['date'].replace('-', '')}")
            next_day = (
                datetime.strptime(item["date"], "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y%m%d")
            lines.append(f"DTEND;VALUE=DATE:{next_day}")

        if item.get("location"):
            lines.append(f"LOCATION:{_escape(item['location'])}")
        lines.append(f"SUMMARY:{_escape(title)}")
        if item.get("note"):
            lines.append(f"DESCRIPTION:{_escape(item['note'])}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    # RFC 5545 要求 CRLF 行尾：iOS / Google 日历对裸 LF 的解析不一致
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
