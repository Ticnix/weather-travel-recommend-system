"""每日智能早报（Day 35）。

把首页仪表盘的能力「主动送达」用户：
今日天气 + 提醒（降水/高温/预警）+ 穿搭建议 + 今日行程与天气冲突提示。

内容策略：
- 推送通知的正文在移动端会被折叠，因此标题给「天气+温度」这类一眼信息，
  正文按 提醒 > 行程冲突 > 穿搭 的优先级压缩为几行
- 无行程时给通用提示，避免空推送（Day 35 要求）
- 组装失败（如天气源全挂）时退化为纯提醒文本，绝不因素材缺失而静默不发

分发策略：
- Celery beat 每小时整点触发一次分发任务，按用户各自设定的推送小时过滤——
  免打扰粒度为「小时」，避免为每个用户单独注册一个定时任务
- 逐用户独立 try：一个用户的数据/推送失败不影响其他人
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.models.notification import NotificationPref
from app.models.user import User
from app.services import notification_service
from app.services.home_service import build_dashboard

logger = logging.getLogger(__name__)


def build_report_text(dashboard: dict[str, Any]) -> tuple[str, str]:
    """从看板数据组装早报文本，返回 (title, body)。"""
    weather = dashboard.get("weather") or {}
    tips = dashboard.get("tips") or []
    outfit = dashboard.get("outfit") or {}
    upcoming = (dashboard.get("itinerary") or {}).get("upcoming") or []
    today = dashboard.get("date")

    desc = weather.get("desc") or "天气"
    tmax, tmin = weather.get("temp_max"), weather.get("temp_min")
    if tmax is not None and tmin is not None:
        temp_part = f"，{tmax:g}~{tmin:g}℃"
    elif tmax is not None:
        temp_part = f"，{tmax:g}℃"
    else:
        temp_part = ""

    title = f"早安｜今日{desc}{temp_part}"

    parts: list[str] = []

    # 1) 提醒：预警(danger)优先于常规提示，最多 2 条
    danger = [t for t in tips if t.get("level") == "danger"]
    normal = [t for t in tips if t.get("level") != "danger"]
    for tip in (danger + normal)[:2]:
        icon = tip.get("icon") or ""
        parts.append(f"{icon} {tip.get('title')}：{tip.get('text')}")

    # 2) 今日行程与天气冲突提示；无行程给通用提示
    today_items = [it for it in upcoming if it.get("date") == today] if today else []
    if today_items:
        for it in today_items[:2]:
            parts.append(f"今日行程「{it.get('title')}」：{it.get('weather_hint')}")
    else:
        parts.append("今天没有安排行程，可按天气自由安排活动")

    # 3) 穿搭建议
    suggestion = outfit.get("suggestion")
    if suggestion:
        parts.append(f"穿搭建议：{suggestion}")

    body = "\n".join(p for p in parts if p)
    return title, body


async def dispatch_to_users(hour: int, factory) -> dict[str, Any]:
    """把早报分发给「已开启早报且推送小时等于 hour」的所有用户。

    factory：async_sessionmaker，由调用方注入——
    Celery 任务传「NullPool 独立引擎」的 factory（与 Web 进程不共享连接池，
    规避 asyncpg 连接跨事件循环失效的坑）；测试传测试库的 factory。
    引擎生命周期由调用方管理，本函数只负责开/关会话。
    """
    async with factory() as db:
        rows = (
            await db.execute(
                select(NotificationPref.user_id, User.email)
                .join(User, User.id == NotificationPref.user_id)
                .where(
                    NotificationPref.morning_enabled.is_(True),
                    NotificationPref.morning_hour == hour,
                    User.is_active.is_(True),
                )
            )
        ).all()
        user_ids = [r[0] for r in rows]

        if not user_ids:
            logger.info("早报分发 hour=%s：没有到点的用户", hour)
            return {"hour": hour, "targets": 0, "sent": 0, "failed": 0}

        sent, failed, details = 0, 0, []
        for uid in user_ids:
            try:
                dashboard = await build_dashboard(uid)
                title, body = build_report_text(dashboard)
                result = await notification_service.notify_user(
                    db, uid, title=title, body=body, url="/"
                )
                channels_ok = any(r.get("status") == "sent" for r in result.values())
                sent += 1 if channels_ok else 0
                details.append({"user_id": uid, "channels": result})
            except Exception as exc:
                failed += 1
                logger.exception("早报分发失败 user_id=%s", uid)
                details.append({"user_id": uid, "error": str(exc)})

        await db.commit()
        logger.info(
            "早报分发完成 hour=%s targets=%s sent=%s failed=%s",
            hour,
            len(user_ids),
            sent,
            failed,
        )
        return {"hour": hour, "targets": len(user_ids), "sent": sent, "failed": failed}
