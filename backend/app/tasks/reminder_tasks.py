"""出发前行程提醒（Day 39）。

**为什么必须有这个模块**：Day 39 的「行程提醒」开关如果背后没有真实发送方，
就是个假开关——用户关掉它什么都不会变，打开它什么也不会来。
所以补一个最小但真实可用的提醒：行程开始前 30 分钟提醒一次。

**「只提醒一次」是怎么保证的**：
任务每 10 分钟跑一次（与 beat 间隔一致），提醒窗口取「距出发 25~35 分钟」。
一条行程的出发时刻必然只落在一个 10 分钟窗口里，天然不会重复，
**不需要在库里额外记「已提醒」状态**——少一份状态就少一类不一致。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.models.itinerary import Itinerary
from app.services import notification_service

logger = logging.getLogger(__name__)

# 用固定的广州时区而不是服务器本地时间：
# Celery 容器通常是 UTC，"今天"会与用户的"今天"差 8 小时，
# 傍晚的行程会被算到第二天去。
CN_TZ = ZoneInfo("Asia/Shanghai")

REMIND_LEAD_MINUTES = 30
WINDOW_LOW = 25.0  # 距出发 25 分钟
WINDOW_HIGH = 35.0  # 到 35 分钟为止（左闭右开，窗口宽度 = beat 间隔）


def parse_start_time(value: str | None) -> time | None:
    """解析 HH:MM；格式不对返回 None（脏数据不该让整个任务挂掉）。"""
    if not value or ":" not in value:
        return None
    try:
        hour, minute = value.split(":")[:2]
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return None


def is_due(start_time: str | None, now: datetime) -> bool:
    """该行程现在是否到了提醒时间（距出发 25~35 分钟）。"""
    parsed = parse_start_time(start_time)
    if parsed is None:
        return False
    start = datetime.combine(now.date(), parsed, tzinfo=now.tzinfo)
    minutes_left = (start - now).total_seconds() / 60
    return WINDOW_LOW <= minutes_left < WINDOW_HIGH


def build_reminder(item: Itinerary) -> tuple[str, str]:
    """提醒文案：尽量短——手机通知栏只显示一两行，写长了等于没写。"""
    where = item.location or item.title
    return (
        f"⏰ {item.start_time} 出发提醒",
        f"「{item.title}」还有约 {REMIND_LEAD_MINUTES} 分钟开始（{where}），记得预留路上时间。",
    )


async def send_due_reminders(db: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    """扫描今天的行程，对到点的发提醒。返回执行摘要。"""
    now = now or datetime.now(CN_TZ)
    today = now.date().isoformat()

    items = (
        (
            await db.execute(
                select(Itinerary).where(
                    Itinerary.date == today,
                    Itinerary.start_time.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    sent = skipped = 0
    for item in items:
        if not is_due(item.start_time, now):
            continue
        title, body = build_reminder(item)
        try:
            # category="itinerary"：被用户的行程提醒开关拦下时会记 skipped
            result = await notification_service.notify_user(
                db, item.user_id, title=title, body=body, url="/itinerary", category="itinerary"
            )
        except Exception as exc:  # noqa: BLE001 单条失败不影响其他行程
            logger.warning("行程提醒发送失败 itinerary_id=%s: %s", item.id, exc)
            continue
        if any(r.get("status") == "sent" for r in result.values()):
            sent += 1
        else:
            skipped += 1

    return {"date": today, "checked": len(items), "sent": sent, "skipped": skipped}


@celery_app.task(name="app.tasks.reminder_tasks.dispatch_itinerary_reminders")
def dispatch_itinerary_reminders() -> dict:
    """beat 每 10 分钟触发：给 30 分钟后要出发的行程发提醒。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(settings.DB_URL, poolclass=NullPool, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _job() -> dict:
        async with factory() as db:
            return await send_due_reminders(db)

    try:
        return asyncio.run(_job())
    finally:
        asyncio.run(engine.dispose())
