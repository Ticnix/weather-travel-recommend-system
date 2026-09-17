"""统一通知发送服务（Day 34）。

统一入口 notify_user(user_id, title, body, url)：
- 并行走所有可用通道（Web Push / 邮件），任何通道失败不影响其他通道
- 每个通道的结果都写入 notification_logs——「发送记录可查询」是
  Day 34 检查清单的硬性要求，成功与失败都留痕
- 通道缺失（未配置 SMTP / 用户未订阅）记为 skipped 而非 failed：
  「功能没开」是产品状态，「发了但失败」才是故障，两者必须分开

Web Push 的失效清理：
推送服务对已失效订阅返回 404/410（用户清了浏览器数据、卸载了授权），
这类订阅留着只会让每次推送白发并被推送服务限流，必须删除。
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import NotificationLog, NotificationPref, PushSubscription
from app.models.user import User

logger = logging.getLogger(__name__)

# 推送服务判定「订阅已失效」的状态码：此时应删除订阅而不是继续重试
_EXPIRED_STATUS = {404, 410}


def _webpush_once(subscription_info: dict[str, Any], payload: str) -> None:
    """单次 Web Push 发送（同步库，调用方负责放线程池）。"""
    webpush(
        subscription_info=subscription_info,
        data=payload,
        vapid_private_key=settings.VAPID_PRIVATE_KEY,
        vapid_claims={"sub": settings.VAPID_CONTACT},
    )


def _smtp_send(to: str, subject: str, html_body: str) -> None:
    """单次邮件发送（同步库，调用方负责放线程池）。"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)


def _email_html(title: str, body: str, url: str | None) -> str:
    link = f'<p><a href="{url}">在浏览器中打开</a></p>' if url else ""
    return f"<h3>{title}</h3><p>{body}</p>{link}"


async def _log_result(
    db: AsyncSession,
    user_id: int,
    channel: str,
    title: str,
    body: str | None,
    url: str | None,
    status: str,
    error: str | None = None,
    category: str = "system",
) -> dict[str, Any]:
    """写入发送记录并返回该通道的结果。"""
    db.add(
        NotificationLog(
            user_id=user_id,
            channel=channel,
            category=category,
            title=title[:200],
            body=body,
            url=url,
            status=status,
            error=error,
        )
    )
    await db.commit()
    return {"channel": channel, "status": status, "error": error}


# 通知类型 → 偏好字段名。system（测试通知等）不在表里 → 一律放行。
CATEGORY_PREF_FIELD: dict[str, str] = {
    "morning": "morning_enabled",
    "alert": "alert_enabled",
    "itinerary": "itinerary_enabled",
}

CATEGORY_LABEL: dict[str, str] = {
    "morning": "每日早报",
    "alert": "天气预警",
    "itinerary": "行程提醒",
    "system": "系统通知",
}


async def get_prefs(db: AsyncSession, user_id: int) -> NotificationPref:
    """取用户通知偏好；没有就按默认值建一条（懒初始化）。

    懒初始化而不是注册时创建：多数用户从不改设置，
    没必要在注册流程里塞一个通知模块的细节。
    """
    pref = (
        await db.execute(select(NotificationPref).where(NotificationPref.user_id == user_id))
    ).scalar_one_or_none()
    if pref is None:
        pref = NotificationPref(user_id=user_id)
        db.add(pref)
        await db.flush()
    return pref


async def category_allowed(db: AsyncSession, user_id: int, category: str) -> tuple[bool, str]:
    """该类型的通知是否允许发给这个用户，返回 (是否允许, 不允许的原因)。"""
    field = CATEGORY_PREF_FIELD.get(category)
    if field is None:
        return True, ""  # system 类不受类型开关约束
    pref = await get_prefs(db, user_id)
    if getattr(pref, field, True):
        return True, ""
    return False, f"用户已关闭「{CATEGORY_LABEL.get(category, category)}」"


async def notify_user(
    db: AsyncSession,
    user_id: int,
    title: str,
    body: str | None = None,
    url: str | None = None,
    category: str = "system",
) -> dict[str, Any]:
    """统一发送入口：先过类型偏好，再顺序走所有可用通道。

    **偏好校验刻意放在这里，而不是各调用方自己检查**：
    发送方有早报、预警、行程提醒……如果每处都记得判开关，早晚漏一个，
    而那种 bug 的表现是「用户明明关了还在收」，最伤信任。
    收口在唯一入口后，调用方只需声明自己是什么类型。

    注意这里**必须顺序执行而不是 asyncio.gather**：
    两个通道共用调用方传入的同一个 AsyncSession，
    而 AsyncSession 不支持并发使用——gather 会让两个协程
    同时抢同一个连接，实测会直接挂起。通知发送本身是毫秒级操作
    （除真实的推送/SMTP 外部请求外都是本地查询），顺序执行没有性能问题。
    """
    allowed, reason = await category_allowed(db, user_id, category)
    if not allowed:
        # 被偏好拦下时仍写一条 skipped 记录：
        # 用户在「推送历史」里能看到"这条被我的设置拦下了"，
        # 而不是去怀疑推送坏了。
        return {
            "web_push": await _log_result(
                db, user_id, "web_push", title, body, url, "skipped", reason, category
            ),
            "email": await _log_result(
                db, user_id, "email", title, body, url, "skipped", reason, category
            ),
        }

    web_push = await _send_web_push(db, user_id, title, body, url, category)
    email = await _send_email(db, user_id, title, body, url, category)
    return {"web_push": web_push, "email": email}


async def _send_web_push(
    db: AsyncSession,
    user_id: int,
    title: str,
    body: str | None,
    url: str | None,
    category: str = "system",
) -> dict[str, Any]:
    # 局部 log()：把「通道 + 用户 + 文案 + 类型」这些重复参数绑掉，
    # 后面每处只关心 status / error，也顺带保证 category 不会漏传
    async def log(status: str, error: str | None = None) -> dict[str, Any]:
        return await _log_result(db, user_id, "web_push", title, body, url, status, error, category)

    subs = (
        (
            await db.execute(
                select(PushSubscription).where(
                    PushSubscription.user_id == user_id,
                    PushSubscription.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    if not subs:
        return await log("skipped", "用户无有效订阅")
    if not settings.VAPID_PRIVATE_KEY:
        return await log("skipped", "VAPID 未配置")

    payload = json.dumps({"title": title, "body": body or "", "url": url or "/"})
    sent, failed, expired, last_error = 0, 0, [], None

    for sub in subs:
        info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
        try:
            # pywebpush 是同步库（内部发 HTTPS 请求），放线程池避免阻塞事件循环
            await asyncio.to_thread(_webpush_once, info, payload)
            sent += 1
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in _EXPIRED_STATUS:
                expired.append(sub.id)
                failed += 1
                last_error = f"订阅已失效（HTTP {status_code}）"
            else:
                # 瞬时失败（网络抖动）自动重试一次
                try:
                    await asyncio.to_thread(_webpush_once, info, payload)
                    sent += 1
                except Exception as exc2:  # noqa: BLE001
                    failed += 1
                    last_error = str(exc2)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            last_error = str(exc)

    # 清理失效订阅：留着只会每次推送白发，还会被推送服务限流
    if expired:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(expired)))
        logger.info("清理失效推送订阅 %s 个 (user_id=%s)", len(expired), user_id)

    if sent:
        status = "sent"
    elif failed:
        status = "failed"
    else:
        status = "skipped"
    return await log(status, last_error)


async def _send_email(
    db: AsyncSession,
    user_id: int,
    title: str,
    body: str | None,
    url: str | None,
    category: str = "system",
) -> dict[str, Any]:
    async def log(status: str, error: str | None = None) -> dict[str, Any]:
        return await _log_result(db, user_id, "email", title, body, url, status, error, category)

    user = await db.get(User, user_id)
    if not (user and user.email):
        return await log("skipped", "用户未绑定邮箱")
    if not settings.SMTP_HOST:
        return await log("skipped", "SMTP 未配置")

    try:
        await asyncio.to_thread(_smtp_send, user.email, title, _email_html(title, body or "", url))
    except Exception as exc:  # noqa: BLE001
        return await log("failed", str(exc))
    return await log("sent")
