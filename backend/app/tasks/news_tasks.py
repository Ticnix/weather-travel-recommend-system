"""气象资讯采集 Celery 任务。

定时从中央气象台等公开数据源采集真实气象资讯并写入 news 表。
与 weather_tasks 同样的处理：Celery 是同步框架，这里复用一个事件循环 +
NullPool 独立引擎，避免 asyncpg 连接跨事件循环失效。
"""

import asyncio
import logging

from app.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task(
    name="app.tasks.news_tasks.collect_weather_news",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def collect_weather_news(
    area: str = "广州",
    with_news: bool = True,
    with_tavily: bool = True,
    with_forecast: bool = True,
) -> dict:
    """采集气象资讯（中央气象台预警 + 中国天气网新闻 + Tavily 本地资讯 + 天气简报）。

    采集依赖多个外部数据源，瞬时报错很常见——这正是自动重试最大的受益场景。
    """

    async def _job() -> dict:
        # 局部导入：避免模块级循环依赖
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.services.weather_news_service import collect_all

        engine = create_async_engine(settings.DB_URL, poolclass=NullPool, pool_pre_ping=True)
        factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as db:
                return await collect_all(
                    db,
                    area=area,
                    with_news=with_news,
                    with_tavily=with_tavily,
                    with_forecast=with_forecast,
                )
        finally:
            await engine.dispose()

    stat = _run(_job())
    logger.info("气象资讯采集完成: %s", stat)
    return {"ok": True, **stat}
