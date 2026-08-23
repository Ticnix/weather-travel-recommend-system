"""数据库初始化脚本。

用法（在 backend 目录、venv 激活后）：
    python -m app.scripts.init_db

功能：
    1. 启用 timescaledb / vector / postgis 三大扩展
    2. 创建全部数据表
    3. 将 weather_history 转换为 TimescaleDB 超表
"""

import asyncio

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.models import (  # noqa: F401 确保模型注册
    Feedback,
    KnowledgeChunk,
    Landmark,
    News,
    User,
    WeatherHistory,
)


async def run() -> None:
    async with engine.begin() as conn:
        print(">>> 启用扩展 ...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

        print(">>> 创建数据表 ...")
        await conn.run_sync(Base.metadata.create_all)

        print(">>> 转换 weather_history 为超表 ...")
        await conn.execute(
            text(
                "SELECT create_hypertable("
                "'weather_history', 'time', "
                "if_not_exists => TRUE, "
                "migrate_data => TRUE"
                ")"
            )
        )

    print(">>> 初始化完成 ✅")


if __name__ == "__main__":
    asyncio.run(run())
