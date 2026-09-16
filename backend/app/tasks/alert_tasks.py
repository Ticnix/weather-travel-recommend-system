"""天气预警轮询 Celery 任务（Day 36）。

beat 每 10 分钟触发一次：拉取各关注城市的预警，识别新增并推送。
引擎在本任务内创建（NullPool 独立引擎，与 Web 进程连接池隔离），
任务结束后 dispose——沿用项目里「Celery 与 Web 进程不共享 asyncpg 连接」的约定。
"""

import asyncio
import logging

from app.celery_app import celery_app
from app.services import alert_service

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.alert_tasks.poll_weather_alerts")
def poll_weather_alerts() -> dict:
    """轮询预警源并推送新增预警。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(settings.DB_URL, poolclass=NullPool, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _job() -> dict:
        async with factory() as db:
            return await alert_service.poll_and_dispatch(db)

    try:
        return _run(_job())
    finally:
        _run(engine.dispose())
