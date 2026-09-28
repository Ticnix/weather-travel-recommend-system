"""出发前行程提醒（Day 39）。

**为什么必须有这个模块**：Day 39 的「行程提醒」开关如果背后没有真实发送方，
就是个假开关——用户关掉它什么都不会变，打开它什么也不会来。
所以补一个最小但真实可用的提醒：行程开始前 30 分钟提醒一次。

**「只提醒一次」是怎么保证的**：
判重不靠时间窗口的巧合，而是查发送记录（见 `_reminder_sent_today`）：
窗口内每 10 分钟扫一次，扫到但今天已经发过就跳过。

**为什么不用「窗口宽度 = beat 间隔」那个更巧的写法**：
它要求 beat 必须准点跑——一旦 beat 延迟、重启，或者 worker 在那一刻忙，
10 分钟的窗口一过，提醒就永远丢了，而且没有任何痕迹（实际踩到过）。
现在窗口放宽到「出发前 35 分钟内」，容忍一次调度抖动，重复由记录拦住。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.models.itinerary import Itinerary
from app.models.notification import NotificationLog
from app.services import notification_service

logger = logging.getLogger(__name__)

# 用固定的广州时区而不是服务器本地时间：
# Celery 容器通常是 UTC，"今天"会与用户的"今天"差 8 小时，
# 傍晚的行程会被算到第二天去。
CN_TZ = ZoneInfo("Asia/Shanghai")

REMIND_LEAD_MINUTES = 30
# 距出发多久以内算「该提醒了」。上限给到 35 分钟而不是掐在 30：
# 多出的 5 分钟是给调度抖动的余量，真正的判重在 _reminder_sent_today
WINDOW_HIGH = 35.0


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
    """该行程现在是否到了提醒时间：还没出发，且距出发不超过 35 分钟。"""
    parsed = parse_start_time(start_time)
    if parsed is None:
        return False
    start = datetime.combine(now.date(), parsed, tzinfo=now.tzinfo)
    minutes_left = (start - now).total_seconds() / 60
    # 已经出发（或正好到点）就不提醒了：出发后再说"记得预留路上时间"没有意义
    return 0 < minutes_left <= WINDOW_HIGH


def build_reminder(item: Itinerary) -> tuple[str, str]:
    """提醒文案：尽量短——手机通知栏只显示一两行，写长了等于没写。"""
    where = item.location or item.title
    return (
        f"⏰ {item.start_time} 出发提醒",
        f"「{item.title}」还有约 {REMIND_LEAD_MINUTES} 分钟开始（{where}），记得预留路上时间。",
    )


async def _reminder_sent_today(db: AsyncSession, item: Itinerary, now: datetime) -> bool:
    """今天是否已经为这条行程处理过提醒（发过、或被偏好拦下）。

    用发送记录判重，而不是给行程表加一个「已提醒」字段：
    历史记录本来就要写，不额外增加写入，也少一份可能与实际不一致的状态。

    只有 **failed** 不算数——网络抖动导致发送失败时，
    下一次扫描（窗口内每 10 分钟一次）应该再试，而不是就此吞掉。
    """
    since = datetime.combine(now.date(), time(0, 0), tzinfo=now.tzinfo).astimezone(UTC)
    title, _ = build_reminder(item)
    found = await db.execute(
        select(NotificationLog.id)
        .where(
            NotificationLog.user_id == item.user_id,
            NotificationLog.category == "itinerary",
            NotificationLog.title == title,
            # 正文前缀带上行程标题，避免"两条行程同一出发时间"互相顶掉
            NotificationLog.body.like(f"「{item.title}」%"),
            NotificationLog.status != "failed",
            NotificationLog.created_at >= since,
        )
        .limit(1)
    )
    return found.scalar_one_or_none() is not None


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
        if await _reminder_sent_today(db, item, now):
            continue  # 今天已经提醒过（或被偏好拦下），不要重复打扰
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
