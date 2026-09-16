"""进程间事件总线（Redis Pub/Sub，Day 36）。

**为什么需要它**：Celery worker 与 Web 进程是**两个独立进程**——
worker 里发现新预警时，挂在 Web 进程上的 SSE 长连接完全感知不到
（进程内队列跨不了进程边界）。Redis 的 Pub/Sub 是这里最小可用的跨进程通道，
项目本来就依赖 Redis，不引入新组件。

**降级立场**（与 core/cache.py 一致）：Redis 不可用时 publish 静默失败、
subscribe 直接结束。实时通道只是「锦上添花」——预警的主通道是 Web Push
与邮件，不该因为 Redis 抖动让整条预警链路挂掉。
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 渠道 → 频道名。目前只有预警，后续有新场景继续加常量即可
ALERT_CHANNEL = "weather:alerts"

# 订阅侧的空闲心跳间隔（秒）：长时间没有消息时发一个 ping，
# 避免 Nginx / 浏览器把空闲长连接掐掉
HEARTBEAT_SECONDS = 15.0


def _client(decode: bool = True) -> Any:
    """构造独立的 Redis 客户端（不共用 cache.py 的连接。

    cache.py 的客户端是「一次失败永久短路」的降级设计——
    它的可用性状态是粘性的，用在长连接订阅上会让 SSE 永久失效。
    """
    import redis.asyncio as aioredis

    return aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=decode,
        socket_connect_timeout=2.0,
    )


async def publish(channel: str, payload: dict[str, Any]) -> bool:
    """发布一条事件（失败返回 False，不抛异常）。"""
    try:
        client = _client()
    except Exception as exc:  # noqa: BLE001 redis 未安装/不可用
        logger.debug("事件总线不可用，跳过发布: %s", exc)
        return False

    try:
        await client.publish(channel, json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as exc:  # noqa: BLE001 发布失败不影响主流程
        logger.warning("事件发布失败 channel=%s: %s", channel, exc)
        return False
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()


async def subscribe(channel: str) -> AsyncIterator[dict[str, Any]]:
    """订阅频道并逐条产出消息；空闲时产出 {"type": "ping"} 作为心跳。

    由 SSE 端点消费（`async for event in subscribe(...)`）。
    """
    client = _client()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
        logger.info("事件订阅已建立: %s", channel)
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
            )
            if message is None:
                yield {"type": "ping"}
                continue
            try:
                yield json.loads(message["data"])
            except (TypeError, ValueError):
                logger.warning("收到无法解析的事件，已忽略")
                continue
    except Exception as exc:  # noqa: BLE001 连接中断即结束订阅（由客户端重连）
        logger.warning("事件订阅中断 channel=%s: %s", channel, exc)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await client.aclose()
