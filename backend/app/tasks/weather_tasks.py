"""气象数据同步 Celery 任务。"""

import asyncio
import logging
from typing import Optional

from app.celery_app import celery_app
from app.services.weather_sync import fetch_and_store

logger = logging.getLogger(__name__)

# Celery solo 池单线程：复用一个事件循环，避免反复 asyncio.run 导致 asyncpg 连接失效。
_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.weather_tasks.sync_weather_hourly")
def sync_weather_hourly(latitude: float | None = None, longitude: float | None = None,
                        location_code: str | None = None) -> dict:
    """每小时同步气象数据（Celery 同步入口）。

    内部用复用的事件循环执行异步 fetch_and_store。
    """
    try:
        bundle = _run(fetch_and_store(latitude, longitude, location_code, use_celery_engine=True))
        logger.info("天气同步成功: loc=%s temp=%s", bundle.location_code, bundle.current.temperature)
        return {
            "ok": True,
            "location": bundle.location_code,
            "temperature": bundle.current.temperature,
            "weather_desc": bundle.current.weather_desc,
            "alerts": len(bundle.alerts),
            "daily": len(bundle.daily),
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("天气同步失败")
        return {"ok": False, "error": str(e)}


@celery_app.task(name="app.tasks.weather_tasks.sync_weather_manual")
def sync_weather_manual(latitude: float | None = None, longitude: float | None = None,
                        location_code: str | None = None) -> dict:
    """手动触发的同步任务（供管理接口调用）。"""
    return sync_weather_hourly(latitude, longitude, location_code)
