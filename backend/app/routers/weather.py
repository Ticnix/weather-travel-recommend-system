"""气象管理接口：手动同步、查询最新实测/预报/预警。"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached
from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.models.user import User
from app.models.weather import WeatherHistory
from app.schemas.weather import SyncResult, WeatherHistoryOut
from app.services import (
    index_service,
    local_weather_service,
    weather_analysis,
    weather_service,
    weather_sync,
)

router = APIRouter(prefix="/api/v1/weather", tags=["气象数据"])

logger = logging.getLogger(__name__)


def _to_out(w: WeatherHistory) -> dict:
    d = WeatherHistoryOut.model_validate(w).model_dump()
    # 统一输出 temp_max / temp_min：
    #   预报行：temperature=最高, feels_like=最低
    #   实测行：temperature=实况温, feels_like=体感温（均作为展示用高/低温）
    d["temp_max"] = w.temperature
    d["temp_min"] = w.feels_like
    return d


@router.post("/sync", response_model=dict)
async def sync_now(current: CurrentUser) -> dict:
    """手动触发气象数据同步（鉴权）。同步拉取并写入时序表，返回结果。"""
    bundle = await weather_sync.fetch_and_store()
    return success(
        SyncResult(
            ok=True,
            location=bundle.location_code,
            temperature=bundle.current.temperature,
            weather_desc=bundle.current.weather_desc,
            alerts=len(bundle.alerts),
            daily=len(bundle.daily),
        ).model_dump(),
        message="同步成功",
    )


@router.post("/sync-async", response_model=dict)
async def sync_async(current: CurrentUser) -> dict:
    """通过 Celery 异步触发同步（鉴权）。立即返回任务 ID。"""
    from app.tasks.weather_tasks import sync_weather_manual

    task = sync_weather_manual.delay()
    return success({"task_id": task.id, "status": "PENDING"}, message="已提交异步同步任务")


@router.post("/sync-history", response_model=dict)
async def sync_history(current: CurrentUser, days: int = 30) -> dict:
    """回补过去 N 天的日统计作为实测写入时序表（鉴权）。默认 30 天。

    用于让「近 30 天天气时间轴」的过去部分有完整数据（Open-Meteo past_days 支持）。
    """
    bundle = await weather_sync.fetch_and_store(past_days=days)
    past = sum(1 for d in bundle.daily if not d.is_forecast)
    future = sum(1 for d in bundle.daily if d.is_forecast)
    return success(
        {"past_days": past, "forecast_days": future, "location": bundle.location_code},
        message=f"历史回补成功：过去 {past} 天 + 未来 {future} 天",
    )


@router.get("/sync-result/{task_id}", response_model=dict)
async def sync_result(task_id: str, current: CurrentUser) -> dict:
    """查询异步同步任务结果（鉴权）。"""
    from app.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return success(
        {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
        }
    )


@router.get("/current", response_model=dict)
async def current_weather(
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "gz",
) -> dict:
    """获取最新实测天气（公开）。

    高频读接口：接 Redis 缓存（5 分钟）降低数据库压力，
    Redis 不可用时自动降级为直查数据库。
    """

    async def _load() -> dict | None:
        latest = await weather_sync.get_latest(location)
        return _to_out(latest) if latest is not None else None

    data = await cached(f"weather:current:{location}", 300, _load)
    if data is None:
        return success(None, message="暂无数据，请先同步")
    return success(data)


@router.get("/local", response_model=dict)
async def local_weather(
    district: str | None = Query(None, description="市辖区名，如「南沙区」"),
    lat: float | None = Query(None, ge=-90, le=90, description="纬度（浏览器定位）"),
    lon: float | None = Query(None, ge=-180, le=180, description="经度（浏览器定位）"),
) -> dict:
    """按「区」或经纬度取当地天气（公开）。

    为什么需要它：广州南北跨度 100+ 公里，南沙和从化同一天能差 3~5℃，
    只按城市中心一个点取数等于让全城用户看同一个数字。

    两种输入任选：
    - `lat` + `lon`：浏览器定位给的坐标（最准），后端逆地理编码成区名再取数
    - `district`：用户手动选的区名（如「南沙区」）

    返回里带 `location.precision`：district=区级 / city=只能到市中心——
    退级时必须让前端能如实说明，而不是让用户以为这就是他家门口的天气。
    """
    try:
        data = await local_weather_service.get_local_weather(
            district=district, lat=lat, lon=lon
        )
    except Exception as exc:  # noqa: BLE001 上游不可用不该抛 500 给前端
        # 必须打日志并带上异常类型：httpx.ConnectError 这类异常的 str() 是空字符串，
        # 只把 str(exc) 丢给前端，用户和排查的人都只会看到"取不到："后面什么也没有
        logger.exception("区级天气取数失败 district=%s lat=%s lon=%s", district, lat, lon)
        raise HTTPException(
            status_code=503,
            detail=(
                f"当地天气暂时取不到（{type(exc).__name__}），请稍后重试；"
                "也可以先用「不用区域定位」看城市天气"
            ),
        ) from exc
    return success(data)


@router.get("/districts", response_model=dict)
async def districts(city: str = Query("广州", description="城市名")) -> dict:
    """某城市可选的市辖区列表（公开，供前端区域选择器使用）。

    `has_coords=False` 的区没有收录区中心坐标，选了只能按市中心取数——
    前端据此在选项上直接标注，避免用户以为选谁都一样准。
    """
    items = local_weather_service.list_districts(city)
    return success({"city": city, "items": items, "total": len(items)})


@router.get("/forecast", response_model=dict)
async def forecast(
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "gz",
) -> dict:
    """获取 7 天预报（公开）。

    预报一天内变化不大，缓存 30 分钟；Redis 不可用时自动降级。
    """

    async def _load() -> dict:
        rows = await weather_sync.list_forecast(location)
        return {"items": [_to_out(r) for r in rows], "total": len(rows)}

    data = await cached(f"weather:forecast:{location}", 1800, _load)
    return success(data)


@router.get("/history", response_model=dict)
async def history(
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "gz",
    limit: int = 24,
) -> dict:
    """获取最近 N 条实测记录（公开）。"""
    rows = await weather_sync.list_recent(location, limit)
    return success({"items": [_to_out(r) for r in rows], "total": len(rows)})


@router.get("/alerts", response_model=dict)
async def alerts(current: CurrentUser) -> dict:
    """获取当前预警（实时拉取，鉴权）。"""
    from app.services.weather_client import weather_client

    bundle = await weather_client.fetch()
    return success(
        {
            "items": [
                {"level": a.level, "type": a.type, "title": a.title, "detail": a.detail}
                for a in bundle.alerts
            ],
            "total": len(bundle.alerts),
        }
    )


async def _user_for(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


@router.post("/sync-archive", response_model=dict)
async def sync_archive(
    current: CurrentUser,
    start: str = Query(..., description="起始日期 YYYY-MM-DD"),
    end: str = Query(..., description="结束日期 YYYY-MM-DD"),
    location: str = Query("gz", description="城市代码"),
) -> dict:
    """回补历史日统计（Open-Meteo 归档接口，鉴权）。

    用途：同比分析需要**去年同期**的数据，而实时接口只能回溯 92 天，
    必须用归档接口把过去的数据补进来。
    """
    from datetime import date as _date

    try:
        start_date = _date.fromisoformat(start)
        end_date = _date.fromisoformat(end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"日期格式应为 YYYY-MM-DD：{exc}") from exc
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="结束日期不能早于起始日期")

    result = await weather_sync.backfill_archive(start_date, end_date, location_code=location)
    # 回补后立即刷新连续聚合，否则新数据要等下一个整点才出现在统计里
    refreshed = await weather_analysis.refresh_daily_aggregate(since=start_date)
    return success({**result, "aggregate_refreshed": refreshed}, message="历史数据回补完成")


@router.get("/analysis/daily", response_model=dict)
async def analysis_daily(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "gz",
    days: int = Query(90, ge=1, le=730),
) -> dict:
    """日粒度趋势序列（读连续聚合 weather_daily）。"""
    items = await weather_analysis.daily_series(db, location, days=days)
    return success({"items": items, "total": len(items), "location_code": location, "days": days})


@router.get("/aqi", response_model=dict)
async def aqi_now(
    current: CurrentUser,
    city: str = Query("广州", max_length=20),
) -> dict:
    """当前空气质量。国内标准按 PM2.5 浓度分级（GB 3095），US AQI 一并返回供参考。"""
    aq = await weather_service.fetch_aqi(city)
    pm25 = aq.pm25
    if pm25 is None:
        level, color = "暂无数据", "default"
    elif pm25 <= 35:
        level, color = "优", "green"
    elif pm25 <= 75:
        level, color = "良", "blue"
    elif pm25 <= 115:
        level, color = "轻度污染", "orange"
    elif pm25 <= 150:
        level, color = "中度污染", "volcano"
    elif pm25 <= 250:
        level, color = "重度污染", "red"
    else:
        level, color = "严重污染", "magenta"
    return success(
        {
            "city": city,
            "pm25": aq.pm25,
            "pm10": aq.pm10,
            "us_aqi": aq.us_aqi,
            "level": level,
            "color": color,
        }
    )


@router.get("/hourly", response_model=dict)
async def hourly_forecast(
    current: CurrentUser,
    city: str = Query("广州", max_length=20),
    hours: int = Query(24, ge=6, le=48),
) -> dict:
    """逐小时预报（默认未来 24 小时），供首页温度曲线使用。

    起点计算用 **Asia/Shanghai 的当前时间**而不是服务器 now()：
    部署机时区常是 UTC，直接比较会把曲线起点切到"8 小时前"。
    点的时间是请求时区的 naive 本地时间，统一抹掉 tzinfo 再比较。
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    points = await weather_service.fetch_hourly(city)
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

    def _naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    upcoming = [p for p in points if _naive(p.time) >= now][:hours]
    return success(
        {
            "city": city,
            "items": [
                {
                    "date": p.time.strftime("%m-%d"),
                    "time": p.time.strftime("%H:%M"),
                    "temperature": p.temperature,
                    "precip_prob": p.precip_prob,
                    "precip": p.precip,
                    "weather_desc": p.weather_desc,
                    "wind_speed": p.wind_speed,
                }
                for p in upcoming
            ],
        }
    )


@router.get("/analysis/compare", response_model=dict)
async def analysis_compare(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    kind: str = Query("yoy", pattern="^(yoy|mom)$", description="yoy=同比 / mom=环比"),
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    location: str = "gz",
) -> dict:
    """月度同比 / 环比（如「今年 9 月比去年同期 +1.2°C」）。

    任一侧没有数据时返回 `available=false` 与原因——
    不拿 0 充数，否则会算出"降水比去年少 100%"这种看起来很真的假结论。
    """
    return success(
        await weather_analysis.compare_month(db, location, kind=kind, year=year, month=month)
    )


@router.post("/analysis/refresh", response_model=dict)
async def analysis_refresh(
    current: CurrentUser,
    since: str | None = Query(None, description="起始日期，缺省为全部"),
) -> dict:
    """手动刷新连续聚合（鉴权）。

    自动刷新策略每小时跑一次，这里提供手动入口：
    回补历史数据或排查数据不一致时不必等下一个整点。
    """
    from datetime import date as _date

    since_date = None
    if since:
        try:
            since_date = _date.fromisoformat(since)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"日期格式应为 YYYY-MM-DD：{exc}") from exc
    ok = await weather_analysis.refresh_daily_aggregate(since=since_date)
    return success({"refreshed": ok}, message="聚合已刷新" if ok else "刷新失败，请查看日志")


@router.get("/indices", response_model=dict)
async def indices(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "广州",
    size: int = index_service.SUMMARY_SIZE,
) -> dict:
    """今日生活指数摘要（鉴权）。

    按**用户体质偏好 + 近期行程**排序后取前 N 条——
    同一批指数，怕冷的人先看到穿衣与感冒，有爬山行程的人先看到运动与紫外线。
    """
    user = await _user_for(db, current.id)
    items = await index_service.get_summary(db, location, user, size)
    return success(
        {
            "items": items,
            "total": len(items),
            "city": location,
            "body_preference": (user.body_preference if user else "normal"),
        }
    )


@router.get("/indices/all", response_model=dict)
async def indices_all(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "广州",
) -> dict:
    """今日全部生活指数（不截断，供「查看全部」展开）。"""
    user = await _user_for(db, current.id)
    records = await index_service.get_indices(db, location)
    items = index_service.rank_indices(
        records,
        (user.body_preference if user else "normal"),
        await index_service.recent_activities(db, current.id),
    )
    return success({"items": items, "total": len(items), "city": location})


@router.get("/indices/history", response_model=dict)
async def indices_history(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    type_code: str = "5",
    location: str = "广州",
    days: int = index_service.HISTORY_DAYS,
) -> dict:
    """某类指数的历史走势（如「这几天紫外线在变强吗」）。"""
    return success(await index_service.get_history(db, location, type_code, days))


@router.get("/stats", response_model=dict)
async def stats(
    current: CurrentUser,
    days: int = 30,
    location: str = "gz",
) -> dict:
    """管理端时序统计：按天聚合温度/湿度/降水均值（鉴权）。"""
    days = max(3, min(days, 365))
    rows = await weather_sync.agg_daily(location_code=location, days=days)
    return success({"items": rows, "total": len(rows)})


@router.get("/admin-list", response_model=dict)
async def admin_list(
    current: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    location: str = "gz",
    date_from: str | None = Query(None, description="起始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    weather: str | None = Query(None, description="天气描述关键字，如：雨/晴"),
    forecast: str | None = Query(None, description="true=预报 / false=实测 / 空=全部"),
) -> dict:
    """管理端气象时序分页查询（鉴权）。支持日期/天气/预报类型筛选。"""
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    fg = None if forecast is None else (forecast.lower() == "true")
    rows, total = await weather_sync.page_records(
        location_code=location,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        weather_desc=weather,
        forecast=fg,
    )
    return success(
        {
            "items": [_to_out(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
