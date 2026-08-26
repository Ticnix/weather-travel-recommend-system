from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# 异步引擎：连接池 + 断线重连检测
engine = create_async_engine(
    settings.DB_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：为每个请求提供一个独立的数据库会话。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库：启用扩展 -> 建表 -> 转换为 TimescaleDB 超表。"""
    from app.db.base import Base
    from app.models import chat_message, clean_task, feedback, itinerary, knowledge, landmark, news, user, user_knowledge, weather  # noqa: F401

    async with engine.begin() as conn:
        # 1. 启用三大扩展（幂等）
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

        # 2. 建表
        await conn.run_sync(Base.metadata.create_all)

        # 3. 将气象时序表转换为超表
        await conn.execute(text("SELECT create_hypertable('weather_history', 'time', if_not_exists => TRUE)"))
