"""FastAPI 应用入口：挂载路由、注册全局异常、健康检查。"""

from fastapi import FastAPI

from app.core.exceptions import register_exception_handlers
from app.core.response import success
from app.routers import (
    chat,
    clean,
    feedback,
    itinerary,
    knowledge,
    news,
    places,
    recommend,
    user_knowledge,
    users,
    weather,
)

app = FastAPI(title="气象出行推荐后端API", version="0.6.0")

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


@app.get("/", tags=["系统"])
async def root() -> dict:
    return success(message="FastAPI 服务启动成功")


@app.get("/health", tags=["系统"])
async def health() -> dict:
    return success(data={"status": "ok"})
