"""通知接口：订阅管理、发送记录、测试推送（均需登录）。"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import event_bus
from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.models.notification import NotificationLog, NotificationPref, PushSubscription
from app.schemas.notification import MorningReportIn, SubscribeIn, UnsubscribeIn
from app.services import notification_service

router = APIRouter(prefix="/api/v1/notifications", tags=["通知"])


@router.get("/vapid-key", response_model=dict)
async def vapid_key(current: CurrentUser) -> dict:
    """前端 pushManager.subscribe 需要的 applicationServerKey。"""
    return success(data={"publicKey": settings.VAPID_PUBLIC_KEY})


@router.post("/subscriptions", response_model=dict)
async def subscribe(
    payload: SubscribeIn,
    current: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """保存/更新推送订阅（以 endpoint 为唯一键，重复订阅则刷新密钥与归属）。"""
    sub = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
        )
    ).scalar_one_or_none()

    if sub:
        sub.user_id = current.id
        sub.p256dh = payload.keys.p256dh
        sub.auth = payload.keys.auth
        sub.user_agent = payload.user_agent
        sub.is_active = True
    else:
        sub = PushSubscription(
            user_id=current.id,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            user_agent=payload.user_agent,
        )
        db.add(sub)
    await db.commit()
    return success(message="订阅成功")


@router.post("/subscriptions/unsubscribe", response_model=dict)
async def unsubscribe(
    payload: UnsubscribeIn,
    current: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """取消订阅（只允许删除自己的订阅）。"""
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.user_id == current.id,
        )
    )
    await db.commit()
    return success(message="已取消订阅")


@router.get("/logs", response_model=dict)
async def my_logs(
    current: CurrentUser,
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 10,
    channel: str | None = None,
) -> dict:
    """当前用户的通知发送记录（成功/失败/跳过都可查）。"""
    page, page_size = max(page, 1), min(max(page_size, 1), 50)
    total = (
        (await db.execute(select(NotificationLog.id).where(NotificationLog.user_id == current.id)))
        .scalars()
        .all()
    )
    query = select(NotificationLog).where(NotificationLog.user_id == current.id)
    if channel:
        query = query.where(NotificationLog.channel == channel)
    items = (
        (
            await db.execute(
                query.order_by(NotificationLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return success(
        data={
            "total": len(total),
            "items": [
                {
                    "id": it.id,
                    "channel": it.channel,
                    "title": it.title,
                    "body": it.body,
                    "url": it.url,
                    "status": it.status,
                    "error": it.error,
                    "created_at": it.created_at.isoformat() if it.created_at else None,
                }
                for it in items
            ],
        }
    )


@router.get("/morning-report", response_model=dict)
async def get_morning_report(
    current: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """查询每日早报偏好（未设置过时返回默认值：开启、7 点推送）。"""
    pref = (
        await db.execute(select(NotificationPref).where(NotificationPref.user_id == current.id))
    ).scalar_one_or_none()
    return success(
        data={
            "enabled": pref.morning_enabled if pref else True,
            "hour": pref.morning_hour if pref else 7,
        }
    )


@router.put("/morning-report", response_model=dict)
async def update_morning_report(
    payload: MorningReportIn,
    current: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """设置每日早报的开关与推送时间（关闭开关后分发任务将不再推送该用户）。"""
    pref = (
        await db.execute(select(NotificationPref).where(NotificationPref.user_id == current.id))
    ).scalar_one_or_none()
    if pref:
        pref.morning_enabled = payload.enabled
        pref.morning_hour = payload.hour
    else:
        pref = NotificationPref(
            user_id=current.id,
            morning_enabled=payload.enabled,
            morning_hour=payload.hour,
        )
        db.add(pref)
    await db.commit()
    return success(data={"enabled": payload.enabled, "hour": payload.hour})


@router.get("/stream")
async def stream_alerts(current: CurrentUser) -> StreamingResponse:
    """预警实时通道（SSE）。

    鉴权说明：浏览器原生 EventSource 无法自定义请求头，因此前端不用它，
    而是用 fetch + ReadableStream 读取本响应（可正常携带 Authorization），
    代价是要自己处理重连与按行解析。

    代理说明：响应头带 `X-Accel-Buffering: no`，避免 Nginx 把 SSE 缓冲成
    一次性输出（那样就完全失去实时性了）。
    """

    async def event_source() -> AsyncIterator[str]:
        # 先回一个注释行：让前端立刻知道连接已建立（而不是等第一条业务消息）
        yield f": connected user={current.id}\n\n"
        async for event in event_bus.subscribe(event_bus.ALERT_CHANNEL):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/test", response_model=dict)
async def send_test(
    current: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """向当前用户发送一条测试通知（走全部可用通道），用于验证订阅链路。"""
    result = await notification_service.notify_user(
        db,
        current.id,
        title="测试通知",
        body="这是一条来自广州天气旅行助手的测试通知，看到它说明订阅链路已打通。",
        url="/",
    )
    return success(data=result)
