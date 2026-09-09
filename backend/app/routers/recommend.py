"""出行 / 穿搭推荐接口（供用户端结果展示页调用，返回结构化 JSON）。

复用标准 Skill 脚本的结构化入口：
- route_planner.plan_structured(origin, destination, city)
- outfit_engine.outfit_structured(city, scene, preference)
"""

from typing import Optional

from fastapi import APIRouter, Query

from app.core.response import success
from app.services.weather_service import fetch_weather
from skills.outfit_recommend.scripts import outfit_engine
from skills.travel_planning.scripts import route_planner

router = APIRouter(prefix="/api/v1/recommend", tags=["智能推荐"])


@router.get("/travel", response_model=dict)
async def recommend_travel(
    origin: str = Query(..., min_length=1, description="出发地，如「广州南站」"),
    destination: str = Query(..., min_length=1, description="目的地，如「广州塔」"),
    city: Optional[str] = Query(None, description="所在城市，默认广州"),
) -> dict:
    """出行规划推荐：返回多套带综合评分的出行方案 + 当日天气。"""
    data = await route_planner.plan_structured(origin, destination, city)
    return success(data=data)


@router.get("/outfit", response_model=dict)
async def recommend_outfit(
    city: Optional[str] = Query(None, description="城市，默认广州"),
    scene: Optional[str] = Query(None, description="出行场景：爬山/逛街/商务/夜游/通勤等"),
    preference: Optional[str] = Query(None, description="个人偏好：怕冷/怕热/正式/运动/休闲/简约/时尚"),
) -> dict:
    """穿搭推荐：返回当日气象参数 + 匹配的穿搭规则 + 知识库参考。"""
    data = await outfit_engine.outfit_structured(city, scene, preference)
    return success(data=data)


# 供前端展示"当前天气概要"，穿搭/出行页可并行拉天气头
@router.get("/weather-head", response_model=dict)
async def weather_head(
    city: Optional[str] = Query(None, description="城市，默认广州"),
) -> dict:
    """今日天气概要（temperature/desc/湿度等），供推荐结果页标题展示。"""
    bundle = await fetch_weather(city or "广州")
    c = bundle.current
    daily = bundle.daily[0] if bundle.daily else None
    return success(
        data={
            "temperature": c.temperature,
            "desc": c.weather_desc,
            "feels_like": c.feels_like,
            "humidity": c.humidity,
            "temp_min": daily.temp_min if daily else None,
            "temp_max": daily.temp_max if daily else None,
        }
    )
