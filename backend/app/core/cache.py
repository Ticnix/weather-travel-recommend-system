"""Redis 业务缓存封装（Day 24 性能与体验优化）。

设计要点：
- 惰性连接：首次使用时才建立 Redis 连接，不影响应用启动
- 静默降级：Redis 未启动 / 连接失败 / 超时时，所有缓存操作自动降级为「不缓存」，
  绝不因缓存组件故障导致业务接口不可用（本机未装 Redis 也可正常开发调试）
- 一次失败即短路：失败后标记不可用，避免后续每个请求都白白等待连接超时
- 统一 JSON 序列化，缓存值需为可被 json 序列化的对象

用法：
    data = await cached("weather:current:gz", 300, _load_from_db)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Any = None
_available: bool = True


async def _get_client() -> Any | None:
    """获取（并缓存）Redis 异步客户端；不可用时返回 None。"""
    global _client, _available
    if not _available:
        return None
    if _client is None:
        try:
            # 局部导入：避免未安装 redis 时应用启动即报错
            import redis.asyncio as aioredis

            _client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 不可用，缓存降级为不生效: %s", exc)
            _available = False
            return None
    return _client


def _mark_unavailable(exc: Exception) -> None:
    """标记缓存不可用，后续请求直接跳过 Redis。"""
    global _available
    if _available:
        logger.warning("Redis 缓存操作失败，后续请求将跳过缓存: %s", exc)
        _available = False


async def cache_get(key: str) -> Any | None:
    """读取缓存；未命中或 Redis 不可用时返回 None。"""
    client = await _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
    except Exception as exc:  # noqa: BLE001
        _mark_unavailable(exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """写入缓存（ttl 秒）；value 为 None 时不写，失败静默忽略。"""
    if value is None:
        return
    client = await _get_client()
    if client is None:
        return
    try:
        await client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        _mark_unavailable(exc)


async def cache_delete(*keys: str) -> None:
    """删除指定缓存键；失败静默忽略。"""
    if not keys:
        return
    client = await _get_client()
    if client is None:
        return
    try:
        await client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        _mark_unavailable(exc)


async def cache_delete_prefix(prefix: str) -> None:
    """按前缀批量删除缓存，用于列表类缓存（key 含分页/筛选参数）的失效。"""
    client = await _get_client()
    if client is None:
        return
    try:
        keys = [k async for k in client.scan_iter(match=f"{prefix}*", count=200)]
        if keys:
            await client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        _mark_unavailable(exc)


async def cached(key: str, ttl: int, factory: Callable[[], Awaitable[Any]]) -> Any:
    """缓存助手：命中直接返回；未命中则执行 factory 并写入缓存。

    factory 返回 None 时不写缓存（避免缓存空结果导致长期脏数据）。
    Redis 不可用时等价于直接调用 factory。
    """
    hit = await cache_get(key)
    if hit is not None:
        return hit
    data = await factory()
    await cache_set(key, data, ttl)
    return data
