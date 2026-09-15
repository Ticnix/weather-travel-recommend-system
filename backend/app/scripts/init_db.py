"""数据库初始化脚本。

用法（在 backend 目录、venv 激活后）：
    python -m app.scripts.init_db

功能：
    1. 启用 timescaledb / vector / postgis 三大扩展
    2. 创建全部数据表
    3. 将 weather_history 转换为 TimescaleDB 超表
    4. 播种默认管理员账号（admin / Admin@123456，幂等）
"""

import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import engine
from app.models import (  # noqa: F401 确保模型注册
    Feedback,
    Itinerary,
    KnowledgeChunk,
    Landmark,
    News,
    User,
    UserKnowledge,
    WeatherHistory,
)

# 默认管理员（仅用于本地联调，生产请修改后重新初始化）
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Admin@123456"


async def _seed_admin(conn: AsyncConnection) -> None:
    """播种默认管理员账号（已存在则跳过，保证幂等）。"""
    exists = await conn.execute(select(User.id).where(User.username == DEFAULT_ADMIN_USERNAME))
    if exists.scalar():
        print(f">>> 管理员 {DEFAULT_ADMIN_USERNAME} 已存在，跳过播种")
        return
    await conn.execute(
        User.__table__.insert().values(
            username=DEFAULT_ADMIN_USERNAME,
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            nickname="系统管理员",
            role="admin",
            is_active=True,
        )
    )
    print(f">>> 已创建默认管理员 {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}")


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

        print(">>> 播种默认管理员 ...")
        await _seed_admin(conn)

    print(">>> 初始化完成 ✅")


if __name__ == "__main__":
    asyncio.run(run())
