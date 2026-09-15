"""每日智能早报 Celery 任务（Day 35）。"""

import asyncio
import datetime
import logging

from app.celery_app import celery_app
from app.services import daily_report

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.report_tasks.dispatch_morning_reports")
def dispatch_morning_reports(hour: int | None = None) -> dict:
    """每小时整点分发早报（按用户各自设定的推送小时过滤）。

    beat 配置为每小时第 0 分触发；不传 hour 时取当前服务器小时。
    引擎在本任务内创建（NullPool，独立于 Web 进程连接池），
    任务结束后 dispose——与 conftest/Day 29 记录的跨事件循环坑同理。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    h = hour if hour is not None else datetime.datetime.now().hour
    engine = create_async_engine(settings.DB_URL, poolclass=NullPool, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        return _run(daily_report.dispatch_to_users(h, factory))
    finally:
        _run(engine.dispose())
