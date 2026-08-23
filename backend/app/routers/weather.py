"""气象管理接口：手动同步、查询最新实测/预报/预警。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.models.weather import WeatherHistory
from app.schemas.weather import SyncResult, WeatherHistoryOut
from app.services import weather_sync

router = APIRouter(prefix="/api/v1/weather", tags=["气象数据"])


def _to_out(w: WeatherHistory) -> dict:
    d = WeatherHistoryOut.model_validate(w).model_dump()
    # 预报行复用字段：temperature=最高, feels_like=最低
    if w.is_forecast:
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


@router.get("/sync-result/{task_id}", response_model=dict)
async def sync_result(task_id: str, current: CurrentUser) -> dict:
    """查询异步同步任务结果（鉴权）。"""
    from app.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return success(
        {"task_id": task_id, "status": result.status, "result": result.result if result.ready() else None}
    )


@router.get("/current", response_model=dict)
async def current_weather(
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "gz",
) -> dict:
    """获取最新实测天气（公开）。"""
    latest = await weather_sync.get_latest(location)
    if latest is None:
        return success(None, message="暂无数据，请先同步")
    return success(_to_out(latest))


@router.get("/forecast", response_model=dict)
async def forecast(
    db: Annotated[AsyncSession, Depends(get_db)],
    location: str = "gz",
) -> dict:
    """获取 7 天预报（公开）。"""
    rows = await weather_sync.list_forecast(location)
    return success({"items": [_to_out(r) for r in rows], "total": len(rows)})


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
