"""天气预警识别与推送（Day 36）。

链路分三步，每一步解决一个具体问题：

1. **识别新增**：上游每次返回的是「当前生效的全部预警」，本身没有"是否新发布"
   这个信息。把它与库里的 fingerprint 比对，只有查不到的才算新预警——
   这是「同一条预警不重复推」的根据。
2. **精准匹配**：按预警城市找受影响用户。
   - 默认城市（广州）：面向所有有推送订阅的用户（本系统就是面向广州的）
   - 其他城市：只推给「未来 7 天行程地点提到该城市」的用户，避免异地打扰
   - 只对**有有效订阅**的用户发：没有订阅的人推了也是 skipped，
     成片的 skipped 记录会把真正的失败淹没
3. **双通道送达**：Web Push / 邮件走 notification_service（离线也能收到）；
   同时在线的用户通过 Redis 事件总线 → SSE 立刻看到（推送有授权门槛与系统级延迟）。

只推送 warn / danger 级别：info 级仅入库留痕，不值得打扰用户。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import event_bus
from app.models.itinerary import Itinerary
from app.models.notification import PushSubscription
from app.models.weather_alert import WeatherAlert
from app.services import notification_service
from app.services.city_dict import lookup_city
from app.services.weather_service import fetch_alerts_with_fallback

logger = logging.getLogger(__name__)

DEFAULT_CITY = "广州"
LOOKAHEAD_DAYS = 7  # 行程向后看几天（与首页保持一致）
PUSH_LEVELS = {"warn", "danger"}  # 只有这两个级别值得打扰用户


def fingerprint(city: str, level: str, title: str) -> str:
    """预警去重键：同一城市 + 同一级别 + 同一标题视为同一条预警。"""
    raw = f"{city}|{level}|{title}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32]


def alert_message(alert: WeatherAlert) -> tuple[str, str]:
    """把预警记录转成通知文案（标题带级别图标，正文截断到适合手机展示的长度）。"""
    icon = "🚨" if alert.level == "danger" else "⚠️"
    title = f"{icon} {alert.city}天气预警：{alert.title}"
    detail = (alert.detail or "").strip() or "请关注当地最新预警信息"
    if len(detail) > 200:
        detail = detail[:197] + "..."
    return title, detail


async def sync_city_alerts(db: AsyncSession, city: str, alerts: list[Any]) -> list[WeatherAlert]:
    """把某城市的当前预警与库比对：返回**新增**的预警记录（已存在的只刷新时间）。

    调用方负责 commit。
    """
    now = datetime.now(UTC)
    rows = (await db.execute(select(WeatherAlert).where(WeatherAlert.city == city))).scalars().all()
    existing = {row.fingerprint: row for row in rows}

    new_alerts: list[WeatherAlert] = []
    for item in alerts:
        fp = fingerprint(city, item.level, item.title)
        row = existing.get(fp)
        if row is not None:
            row.last_seen_at = now  # 仍在生效：刷新「最近一次看到」
            continue

        row = WeatherAlert(
            fingerprint=fp,
            city=city,
            level=item.level,
            type=getattr(item, "type", "") or "",
            title=item.title,
            detail=getattr(item, "detail", None),
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(row)
        new_alerts.append(row)

    if new_alerts:
        await db.flush()  # 拿到自增 id，SSE 事件里要用
    return new_alerts


async def match_users(db: AsyncSession, city: str) -> list[int]:
    """找出该城市预警要通知的用户（只含有有效推送订阅的）。"""
    subscribed = (
        select(PushSubscription.user_id).where(PushSubscription.is_active.is_(True)).distinct()
    )

    if city == DEFAULT_CITY:
        return list((await db.execute(subscribed)).scalars().all())

    today = date.today().isoformat()
    end = (date.today() + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    rows = await db.execute(
        select(Itinerary.user_id)
        .where(
            Itinerary.user_id.in_(subscribed),
            Itinerary.date >= today,
            Itinerary.date <= end,
            Itinerary.location.ilike(f"%{city}%"),
        )
        .distinct()
    )
    return list(rows.scalars().all())


async def dispatch_alert(
    db: AsyncSession, alert: WeatherAlert, user_ids: list[int]
) -> dict[str, Any]:
    """把一条预警推给指定用户，并广播到实时通道。"""
    title, body = alert_message(alert)
    delivered = 0
    for user_id in user_ids:
        try:
            result = await notification_service.notify_user(
                db, user_id, title=title, body=body, url="/", category="alert"
            )
            if any(r.get("status") == "sent" for r in result.values()):
                delivered += 1
        except Exception as exc:  # noqa: BLE001 单个用户失败不影响其他人
            logger.warning("预警推送失败 user_id=%s: %s", user_id, exc)

    # 实时通道：广播给所有在线连接（前端收到后弹提醒）。
    # 这里不按用户过滤——本系统面向广州单城，在线连接即目标用户；
    # 若将来多城运营，改成 per-user 频道即可。
    await event_bus.publish(
        event_bus.ALERT_CHANNEL,
        {
            "event": "weather_alert",
            "id": alert.id,
            "city": alert.city,
            "level": alert.level,
            "alert_type": alert.type,
            "title": alert.title,
            "detail": alert.detail,
            "at": datetime.now(UTC).isoformat(),
        },
    )

    alert.notified_at = datetime.now(UTC)
    alert.notified_count = delivered
    await db.commit()
    return {"users": len(user_ids), "delivered": delivered}


async def collect_watch_cities(db: AsyncSession) -> list[str]:
    """要轮询预警的城市 = 默认城市 + 用户近期行程涉及的城市。"""
    cities = {DEFAULT_CITY}
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    locations = (
        (
            await db.execute(
                select(Itinerary.location)
                .where(
                    Itinerary.date >= today,
                    Itinerary.date <= end,
                    Itinerary.location.is_not(None),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    for location in locations:
        info = lookup_city(location)
        if info:
            cities.add(info.name)
    return sorted(cities)


async def poll_and_dispatch(db: AsyncSession, cities: list[str] | None = None) -> dict[str, Any]:
    """轮询各城市预警 → 识别新增 → 匹配用户 → 推送。返回执行摘要。"""
    targets = cities or await collect_watch_cities(db)
    summary: dict[str, Any] = {
        "cities": targets,
        "new_alerts": 0,
        "pushed_alerts": 0,
        "notified_users": 0,
        "details": [],
    }

    for city in targets:
        try:
            alerts = await fetch_alerts_with_fallback(city)
        except Exception as exc:  # noqa: BLE001 单个城市拉取失败不影响其他城市
            logger.warning("轮询 %s 预警失败: %s", city, exc)
            continue

        new_alerts = await sync_city_alerts(db, city, alerts)
        for alert in new_alerts:
            summary["new_alerts"] += 1
            if alert.level not in PUSH_LEVELS:
                summary["details"].append(
                    {"city": city, "title": alert.title, "action": "仅入库（info 级不打扰）"}
                )
                continue

            user_ids = await match_users(db, city)
            if not user_ids:
                summary["details"].append(
                    {"city": city, "title": alert.title, "action": "无订阅用户，仅入库"}
                )
                continue

            stat = await dispatch_alert(db, alert, user_ids)
            summary["pushed_alerts"] += 1
            summary["notified_users"] += stat["delivered"]
            summary["details"].append(
                {"city": city, "title": alert.title, "action": f"已推送 {stat['delivered']} 人"}
            )

        await db.commit()

    logger.info(
        "预警轮询完成 cities=%s new=%s pushed=%s users=%s",
        summary["cities"],
        summary["new_alerts"],
        summary["pushed_alerts"],
        summary["notified_users"],
    )
    return summary
