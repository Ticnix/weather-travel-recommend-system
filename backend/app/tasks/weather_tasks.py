"""气象数据同步 Celery 任务。"""

import asyncio
import logging

from app.celery_app import celery_app
from app.services.weather_sync import fetch_and_store

logger = logging.getLogger(__name__)

# Celery solo 池单线程：复用一个事件循环，避免反复 asyncio.run 导致 asyncpg 连接失效。
_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task(
    name="app.tasks.weather_tasks.sync_weather_hourly",
    # 失败重试：指数退避（1s/2s/4s...上限 60s）+ 抖动，最多 3 次。
    # 前提是异常必须抛出 Celery 才能感知——所以函数体内不再吞异常。
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def sync_weather_hourly(
    latitude: float | None = None, longitude: float | None = None, location_code: str | None = None
) -> dict:
    """每小时同步气象数据（Celery 同步入口）。

    失败处理：异常向上抛给 Celery —— 触发 autoretry 重试，
    重试耗尽后任务标记 FAILURE 并触发全局告警（celery_app.task_failure）。
    此前这里曾捕获异常返回 {"ok": False}，Celery 会把失败当成 SUCCESS，
    重试与告警全部失效——「吞异常」比「不处理」更隐蔽。
    """
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


@celery_app.task(name="app.tasks.weather_tasks.sync_weather_manual")
def sync_weather_manual(
    latitude: float | None = None, longitude: float | None = None, location_code: str | None = None
) -> dict:
    """手动触发的同步任务（供管理接口调用）。"""
    return sync_weather_hourly(latitude, longitude, location_code)
