"""测试全局配置与公共 fixture。

三个关键设计（也是这套测试能不能"跑得干净、跑得独立"的关键）：

1. **独立测试库**
   通过环境变量把 `DB_URL` 指向 `weather_db_test`，与开发库**物理隔离**，
   测试怎么造数据都不会污染真实数据。
   ⚠️ 必须在导入 `app` 之前设置——`settings` 是模块级单例，导入即固化。

2. **为什么不用「同库 + 事务回滚」**
   项目里部分 Service（如 `chat_history_service.add_message`）在未传 `db` 时
   会**自建 AsyncSession 并 commit**，这类写入不受 FastAPI 依赖覆盖影响，
   事务回滚方案挡不住，会真写进开发库。所以改用独立库 + 自动清表。

3. **外部依赖必须 Mock**
   和风 / 高德 / Tavily / LLM 全部用 `respx` 拦截，
   测试不依赖网络与 API Key（断网也能全绿）。
   `respx_mock` 未匹配到的外部请求会直接报错——这本身就是一道防线，
   能暴露出"某个用例偷偷访问了真实网络"。
"""

from __future__ import annotations

import os

# ⚠️ 必须在导入 app 之前设置：settings 在导入时就读取环境变量
TEST_DB_NAME = "weather_db_test"
TEST_DB_URL = os.environ.get(
    "TEST_DB_URL",
    f"postgresql+asyncpg://admin:123456@127.0.0.1:5432/{TEST_DB_NAME}",
)
os.environ["DB_URL"] = TEST_DB_URL
# 让应用自身的 engine 也走 NullPool（见 app/db/session.py 的说明）：
# pytest-asyncio 每个用例新建事件循环，连接池缓存会跨 loop 失效
os.environ["DB_USE_NULLPOOL"] = "1"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  # 注册所有模型到 Base.metadata
from app.db.base import Base
from app.main import app

# ===== 测试专用引擎（连测试库）=====
# ⚠️ 必须用 NullPool：pytest-asyncio 为每个用例创建独立事件循环，
# 而连接池会缓存「绑定旧 loop」的连接，下一个用例复用时即报
# `RuntimeError: Event loop is closed`（asyncpg 的经典坑，
# 项目在 Celery 侧也踩过同一个问题，那里同样用 NullPool 解决）。
_engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False)

# 普通用户 / 管理员测试账号
USER_CRED = {"username": "tester", "password": "Test@123456"}
ADMIN_CRED = {"username": "admin_t", "password": "Admin@123456"}


async def _ensure_database() -> None:
    """确保测试库存在（不存在则创建）。"""
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await admin_engine.dispose()


async def _prepare_schema() -> None:
    """建扩展 + **重建**表。

    测试库**不建 TimescaleDB 超表**：超表是时序优化手段，
    对验证 CRUD 与业务逻辑没有影响，省去这一步能让测试启动更快、依赖更少。

    ⚠️ 每次会话先 drop 再 create，而不是只 `create_all`：
    `create_all` 只会创建"缺失的表"，**不会给已存在的表补新增的列**。
    一旦模型加了字段（如 Day 37 的 `users.body_preference`），
    本地遗留的测试库就会报 `UndefinedColumn`——现象很迷惑：
    代码没错、开发库迁移也跑了，就是测试库"老了"。
    测试库本就是一次性的，重建比兼容旧结构省心得多。

    护栏：库名必须以 `_test` 结尾才允许重建，避免误伤真实库。
    """
    if not TEST_DB_NAME.endswith("_test"):
        raise RuntimeError(f"拒绝对非测试库执行重建：{TEST_DB_NAME}")

    async with _engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def pytest_sessionstart(session) -> None:
    """整个测试会话开始时：建库 + 建表（只做一次）。"""
    import asyncio

    asyncio.run(_ensure_database())
    asyncio.run(_prepare_schema())


# ===== fixture =====


@pytest_asyncio.fixture
async def db():
    """直连测试库的会话，用于**直接造数据 / 断言落库结果**。"""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """每个用例结束后清空所有表，保证用例之间互不干扰。

    TRUNCATE ... RESTART IDENTITY CASCADE：
    - RESTART IDENTITY 让自增 ID 归零，避免不同用例间 ID 依赖
    - CASCADE 一并清空有外键引用的表
    """
    yield
    async with _engine.begin() as conn:
        names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        if names:
            await conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def client():
    """ASGI 直连客户端：不启动真实服务器，直接调 FastAPI 应用。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _register_and_login(client: AsyncClient, cred: dict) -> str:
    """注册并登录，返回 access_token（已存在则直接登录）。"""
    await client.post("/api/v1/users/register", json=cred)
    resp = await client.post("/api/v1/users/login", json=cred)
    return resp.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def user_token(client) -> str:
    """普通用户 token。"""
    return await _register_and_login(client, USER_CRED)


@pytest_asyncio.fixture
async def auth_headers(user_token) -> dict:
    """普通用户鉴权头。"""
    return {"Authorization": f"Bearer {user_token}"}


@pytest_asyncio.fixture
async def admin_headers(client, db) -> dict:
    """管理员鉴权头。

    直接改库把角色置为 admin，而不依赖管理端接口——
    测试夹具不应该依赖"被测系统"的另一个功能，否则一个坏了全坏。
    """
    await client.post("/api/v1/users/register", json=ADMIN_CRED)
    await db.execute(
        text("UPDATE users SET role = 'admin' WHERE username = :u"), {"u": ADMIN_CRED["username"]}
    )
    await db.commit()
    return {"Authorization": f"Bearer {await _register_and_login(client, ADMIN_CRED)}"}
