"""出行 / 穿搭推荐接口（供用户端结果展示页调用，返回结构化 JSON）。

复用标准 Skill 脚本的结构化入口：
- route_planner.plan_structured(origin, destination, city)
- outfit_engine.outfit_structured(city, scene, preference)
"""

from fastapi import APIRouter, Query

from app.core.cache import cached
from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.response import success
from app.schemas.itinerary import PlanRequest
from app.services import itinerary_risk, outfit_inspiration
from app.services.weather_service import fetch_weather
from skills.itinerary_planner.scripts import planner
from skills.outfit_recommend.scripts import outfit_engine
from skills.travel_planning.scripts import route_planner

router = APIRouter(prefix="/api/v1/recommend", tags=["智能推荐"])


@router.get("/travel", response_model=dict)
async def recommend_travel(
    origin: str = Query(..., min_length=1, description="出发地，如「广州南站」"),
    destination: str = Query(..., min_length=1, description="目的地，如「广州塔」"),
    city: str | None = Query(None, description="所在城市，默认广州"),
    origin_lng: float | None = Query(None, description="出发地经度（前端选点后直传）"),
    origin_lat: float | None = Query(None, description="出发地纬度"),
    destination_lng: float | None = Query(None, description="目的地经度"),
    destination_lat: float | None = Query(None, description="目的地纬度"),
) -> dict:
    """出行规划推荐：返回多套带综合评分的出行方案 + 当日天气。

    传入选点坐标时**直接按坐标规划、跳过地名解析**，
    避免手输地名识别不出来导致规划失败。
    """
    o_point = (
        {"lng": origin_lng, "lat": origin_lat, "formatted": origin}
        if origin_lng is not None and origin_lat is not None
        else None
    )
    d_point = (
        {"lng": destination_lng, "lat": destination_lat, "formatted": destination}
        if destination_lng is not None and destination_lat is not None
        else None
    )
    data = await route_planner.plan_structured(origin, destination, city, o_point, d_point)
    return success(data=data)


@router.get("/outfit", response_model=dict)
async def recommend_outfit(
    city: str | None = Query(None, description="城市，默认广州"),
    scene: str | None = Query(None, description="出行场景：爬山/逛街/商务/夜游/通勤等"),
    preference: str | None = Query(
        None, description="个人偏好：怕冷/怕热/正式/运动/休闲/简约/时尚"
    ),
) -> dict:
    """穿搭推荐：返回当日气象参数 + 匹配的穿搭规则 + 知识库参考。"""
    data = await outfit_engine.outfit_structured(city, scene, preference)
    return success(data=data)


@router.get("/outfit/posts", response_model=dict)
async def outfit_posts(
    city: str | None = Query(None, description="城市，默认广州"),
    scene: str | None = Query(None, description="出行场景：爬山/逛街/商务等"),
    preference: str | None = Query(None, description="个人偏好"),
) -> dict:
    """穿搭灵感：社交平台（抖音为主）的真实搭配参考 + 各平台搜索直达入口。

    与 `/outfit` 拆开是因为联网搜索耗时较长（数秒），
    前端可以先渲染规则建议、再异步加载这一块，避免整体变慢。

    小红书对搜索引擎屏蔽，站内笔记拿不到，因此改为提供其搜索页直达链接。
    结果按（城市, 场景, 偏好）缓存 30 分钟，避免反复消耗搜索额度。
    """
    cache_key = f"outfit:posts:{city}:{scene}:{preference}"

    async def _load() -> dict:
        # 先取当前天气参数，让搜索词贴合「当下这个温度」该穿什么
        outfit = await outfit_engine.outfit_structured(city, scene, preference)
        weather = outfit.get("weather", {})
        return await outfit_inspiration.fetch_outfit_ideas(
            city=city or "广州",
            scene=scene,
            preference=preference,
            temp=float(weather.get("temp") or 25),
            weather_desc=weather.get("desc") or "",
        )

    data = await cached(cache_key, 1800, _load)
    return success(data=data)


# 供前端展示"当前天气概要"，穿搭/出行页可并行拉天气头
@router.get("/weather-head", response_model=dict)
async def weather_head(
    city: str | None = Query(None, description="城市，默认广州"),
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


@router.post("/plan", response_model=dict)
async def plan_trip(payload: PlanRequest, current: CurrentUser) -> dict:
    """AI 一键排行程：按自然语言需求生成结构化行程。

    **只生成、不落库**——是否保存由用户在界面上确认（另走
    `POST /api/v1/itinerary/batch`）。理由：AI 排出来的行程是"提案"，
    直接写进用户的行程表等于替他做了决定，而改起来比删掉更烦。

    返回里包含 `adjustments`：因天气被调整的项要**明确告诉用户**，
    静默替换掉他刚看到的内容比不调整更让人困惑。
    """
    result = await planner.generate(payload.query)
    return success(result)


_SEVERE_HINT = ("雷", "大风", "沙尘", "冰雹", "暴雨")


def _best_days_reason(day) -> str:
    """与 score_day 的排除规则一一对应：不合适的日子要能说出为什么。"""
    desc = (getattr(day, "weather_desc", None) or "").strip()
    precip = getattr(day, "precipitation_sum", None) or 0
    tmax = getattr(day, "temp_max", None)
    tmin = getattr(day, "temp_min", None)
    if any(w in desc for w in _SEVERE_HINT):
        return f"天气不稳（{desc or '强对流'}），不宜户外"
    if precip >= settings.RAIN_ALERT_MM:
        return f"降水约 {precip:g}mm，大概率淋雨"
    if tmax is not None and tmax >= settings.HEAT_ALERT_C:
        return f"最高 {tmax:g}℃，高温时段不宜户外"
    if tmax is None or tmin is None:
        return "当天预报数据不全，无法评估"
    return "温度或降水条件一般"


@router.get("/best-days", response_model=dict)
async def best_days(
    current: CurrentUser,
    location: str = Query("gz", max_length=20),
    days: int = Query(7, ge=1, le=7),
) -> dict:
    """未来 days 天里哪几天适合出行（按适配度从高到低）。

    复用 itinerary_risk.score_day（与行程风险页同一套打分）；
    不合适的日子**仍返回**并带 reason——"为什么不行"比悄悄消失有用。
    必须用 fetch_weather().daily（DailyForecast 才有 temp_max 等字段），
    WeatherHistory 表行没有这些字段，score_day 会把每天都判"数据不全"。
    """
    bundle = await fetch_weather(None)
    rows = bundle.daily[:days]
    items = []
    for day in rows:
        score = itinerary_risk.score_day(day)
        items.append(
            {
                "date": day.date,
                "suitable": score is not None,
                "score": score,
                "weather_desc": (getattr(day, "weather_desc", None) or "").strip(),
                "temp_min": getattr(day, "temp_min", None),
                "temp_max": getattr(day, "temp_max", None),
                "reason": None if score is not None else _best_days_reason(day),
            }
        )
    items.sort(key=lambda x: (0, x["score"]) if x["suitable"] else (1, 0))
    return success(
        {
            "items": items,
            "location_code": location,
            "suitable_total": sum(1 for x in items if x["suitable"]),
        }
    )
