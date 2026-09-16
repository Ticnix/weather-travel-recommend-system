"""气象管理接口：手动同步、查询最新实测/预报/预警。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached
from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.models.user import User
from app.models.weather import WeatherHistory
from app.schemas.weather import SyncResult, WeatherHistoryOut
from app.services import index_service, weather_sync

router = APIRouter(prefix="/api/v1/weather", tags=["气象数据"])


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
