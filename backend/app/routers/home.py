"""首页仪表盘接口。

把用户最关心的几块内容聚合到一个接口，首页一次请求即可完整渲染：
实时天气、今日提醒、穿搭建议、近期行程（含逐条天气提醒）。
"""

from fastapi import APIRouter, Query

from app.core.deps import OptionalUser
from app.core.response import success
from app.services import home_service

router = APIRouter(prefix="/api/v1/home", tags=["首页"])


@router.get("/dashboard", response_model=dict)
async def dashboard(
    current: OptionalUser = None,
    city: str | None = Query(None, description="城市，默认广州"),
) -> dict:
    """首页聚合数据。

    可选鉴权：未登录返回天气 + 通用建议；登录后额外返回近期行程及其天气提醒。
    """
    data = await home_service.build_dashboard(current.id if current else None, city)
    return success(data=data)
