"""FastAPI 应用入口：可观测性、路由挂载、全局异常、健康检查。"""

import asyncio

from fastapi import FastAPI, Response
from sqlalchemy import text

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.observability import metrics, setup_observability
from app.core.response import success
from app.db.session import AsyncSessionLocal
from app.routers import (
    chat,
    clean,
    feedback,
    home,
    itinerary,
    knowledge,
    news,
    notes,
    places,
    recommend,
    user_knowledge,
    users,
    weather,
)

app = FastAPI(title="气象出行推荐后端API", version="0.6.0")

# 可观测性：JSON 结构化日志 + request_id 贯穿 + 请求指标（必须最先挂载）
setup_observability(app)

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载业务路由
app.include_router(users.router)
app.include_router(news.router)
app.include_router(feedback.router)
app.include_router(weather.router)
app.include_router(clean.router)
app.include_router(knowledge.router)
app.include_router(user_knowledge.router)
app.include_router(itinerary.router)
app.include_router(chat.router)
app.include_router(recommend.router)
app.include_router(places.router)
app.include_router(notes.router)
app.include_router(home.router)


@app.get("/", tags=["系统"])
async def root() -> dict:
    return success(message="FastAPI 服务启动成功")


@app.get("/health", tags=["系统"])
async def health(response: Response) -> dict:
    """部署探针：检查核心依赖，任一不可用返回 503。

    为什么检查失败是 503 而不是「200 + 明细字段」：
    deploy.sh 用 HTTP 状态码判断「新版本能不能服务」（curl -f 只认 5xx 为失败）。
    依赖挂了还返回 200，部署脚本会误判上线成功——健康检查的语义必须是
    「这个实例现在能不能正常工作」。

    为什么不检查外部 API（和风/高德）：
    第三方抖动是常态且业务层已有降级兜底；把它纳入健康检查会让部署回滚
    被第三方故障误触发。这里只检查「自己说了算」的核心依赖。

    注意：Redis 检查使用独立短连接，不走 cache.py——后者是「一次失败
    永久短路」的静默降级设计，无法反映 Redis 的实时状态。
    """
    checks: dict[str, str] = {}

    try:
        async with asyncio.timeout(2):
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:  # noqa: BLE001 依赖故障必须降级为 503，不能 500
        checks["db"] = f"fail:{type(exc).__name__}"

    try:
        async with asyncio.timeout(2):
            # 局部导入：跟随 cache.py 的容错模式（redis 未安装时不影响启动）
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
                decode_responses=True,
            )
            try:
                await client.ping()
            finally:
                await client.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"fail:{type(exc).__name__}"

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = 503
    return success(data={"status": "ok" if healthy else "degraded", "checks": checks})


@app.get("/metrics", tags=["系统"])
async def metrics_endpoint() -> dict:
    """轻量监控：按路由聚合的请求数 / 错误数 / 平均耗时（进程内计数，重启归零）。"""
    return success(data=metrics.snapshot())
