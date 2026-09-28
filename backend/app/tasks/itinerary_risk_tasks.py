"""行程 × 天气冲突扫描的定时入口（Day 51）。

**为什么这一天只扫描、不推送**：推送留到 Day 52 接（复用 `notification_service`
的类型开关与判重）。把"扫得对不对"和"发得出去吗"拆成两天，
否则提醒没来时你分不清是规则写错了还是推送坏了。

扫描策略：一次查出窗口内**所有用户**的行程，天气只调一次（全城共用一份预报），
再按用户分组。这样 N 个用户也只花 1 次外部请求。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import settings
from app.models.itinerary import Itinerary
from app.models.notification import NotificationLog
from app.services import notification_service, weather_service
from app.services.itinerary_risk import _plus_days, _today, scan_items

logger = logging.getLogger(__name__)


async def _already_notified(db, user_id: int, title: str, today: str) -> bool:
    """今天是否已为这条冲突发过通知（判重）。

    与行程提醒同一套思路：**不靠"扫描窗口的巧合"**，而是查发送记录。
    窗口每 12 小时扫一次，早上发过之后傍晚必然再扫到同一条——
    没有这道判重，用户会被同一条预警打扰两遍。

    只有 `failed` 不算数：网络抖动导致没发出去时，下一次扫描应该重试。
    """
    from datetime import UTC, date, datetime, time
    from zoneinfo import ZoneInfo

    since = datetime.combine(
        date.fromisoformat(today), time(0, 0), tzinfo=ZoneInfo("Asia/Shanghai")
    ).astimezone(UTC)
    found = await db.execute(
        select(NotificationLog.id)
        .where(
            NotificationLog.user_id == user_id,
            NotificationLog.category == "itinerary_risk",
            NotificationLog.title == title,
            NotificationLog.status != "failed",
            NotificationLog.created_at >= since,
        )
        .limit(1)
    )
    return found.scalar_one_or_none() is not None


async def scan_all_risks(db) -> dict:
    """扫描窗口内所有行程，返回执行摘要（含每条命中的建议文案）。"""
    today = _today()
    horizon = _plus_days(today, settings.RISK_SCAN_DAYS)

    rows = (
        (
            await db.execute(
                select(Itinerary).where(
                    Itinerary.date >= today,
                    Itinerary.date <= horizon,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return {"date": today, "checked": 0, "hits": 0, "details": []}

    items = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "title": r.title,
            "date": r.date,
            "start_time": r.start_time,
            "location": r.location,
            "activity": r.activity,
        }
        for r in rows
    ]

    try:
        bundle = await weather_service.fetch_weather(None)
    except Exception as exc:  # noqa: BLE001 天气拿不到就不报，绝不误报
        logger.warning("行程冲突扫描：取天气失败，本次跳过：%s", exc)
        return {"date": today, "checked": len(items), "hits": 0, "details": [], "error": str(exc)}

    forecast = {d.date: d for d in bundle.daily}
    risks = scan_items(items, forecast, today=today)

    owner_of = {i["id"]: i["user_id"] for i in items}
    sent = skipped = failed = 0
    for risk in risks:
        user_id = owner_of.get(risk["itinerary_id"])
        if user_id is None:
            continue
        # 逐条落日志：排查"为什么没收到提醒"时，这里能直接看到"当时到底有没有扫出来"
        logger.info(
            "行程冲突命中 user=%s itinerary=%s date=%s kind=%s | %s",
            user_id,
            risk["itinerary_id"],
            risk["date"],
            risk["kind"],
            risk["title"],
        )
        if await _already_notified(db, user_id, risk["title"], today):
            skipped += 1
            continue
        try:
            # category="itinerary_risk"：被用户的类型开关拦下时，notify_user 会记 skipped 并写明原因
            result = await notification_service.notify_user(
                db,
                user_id,
                title=risk["title"],
                body=risk["body"],
                url="/itinerary",
                category="itinerary_risk",
            )
        except Exception as exc:  # noqa: BLE001 单条失败不影响其他行程
            failed += 1
            logger.warning("行程预警发送失败 user=%s: %s", user_id, exc)
            continue
        if any(r.get("status") == "sent" for r in result.values()):
            sent += 1
        else:
            skipped += 1

    return {
        "date": today,
        "checked": len(items),
        "hits": len(risks),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "details": risks,
    }


@celery_app.task(name="app.tasks.itinerary_risk_tasks.scan_itinerary_risks")
def scan_itinerary_risks() -> dict:
    """beat 每天 7:05 / 18:05 触发：提前发现行程与预报的冲突。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(settings.DB_URL, poolclass=NullPool, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _job() -> dict:
        async with factory() as db:
            return await scan_all_risks(db)

    try:
        return asyncio.run(_job())
    finally:
        asyncio.run(engine.dispose())
