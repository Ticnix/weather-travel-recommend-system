"""气象数据同步服务：把 WeatherBundle 写入 weather_history 时序表。

- 实时数据 → is_forecast=False 的一行
- 7 天预报 → is_forecast=True 的 7 行
- 预警暂不入库，由接口实时返回（后续可建 alerts 表）
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.weather import WeatherHistory
from app.services.weather_client import WeatherBundle, weather_client


def _make_session() -> async_sessionmaker[AsyncSession]:
    """为 Celery 任务创建独立引擎（NullPool，避免跨事件循环复用连接池）。"""
    engine = create_async_engine(settings.DB_URL, poolclass=NullPool, pool_pre_ping=True)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def fetch_and_store(
    latitude: float | None = None,
    longitude: float | None = None,
    location_code: str | None = None,
    use_celery_engine: bool = False,
) -> WeatherBundle:
    """拉取气象数据并写入时序表，返回原始数据包。

    use_celery_engine=True 时使用独立的 NullPool 引擎，避免 Celery 跨 asyncio.run 复用连接池出错。
    """
    bundle = await weather_client.fetch(latitude, longitude, location_code)
    factory = _make_session() if use_celery_engine else AsyncSessionLocal
    async with factory() as db:
        await store_weather(db, bundle)
        await db.commit()
    return bundle


async def store_weather(db: AsyncSession, bundle: WeatherBundle) -> None:
    """将一次拉取的数据写入时序表（按 time+location_code upsert）。"""
    rows: list[dict] = []

    # 实测行
    c = bundle.current
    rows.append(
        {
            "time": c.time,
            "location_code": bundle.location_code,
            "temperature": c.temperature,
            "feels_like": c.feels_like,
            "humidity": c.humidity,
            "pressure": c.pressure,
            "wind_speed": c.wind_speed,
            "wind_direction": c.wind_direction,
            "weather_code": c.weather_code,
            "weather_desc": c.weather_desc,
            "precipitation": c.precipitation,
            "visibility": c.visibility,
            "is_forecast": False,
            "raw": {"current": c.raw},
        }
    )

    # 7 天预报行（时间为当天 08:00 UTC 的近似，作为日预报时间戳）
    for f in bundle.daily:
        # 用日期 + 00:00:00Z 作为预报时间戳，便于按天去重
        try:
            day = datetime.strptime(f.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        rows.append(
            {
                "time": day,
                "location_code": bundle.location_code,
                "temperature": f.temp_max,  # 预报行存日最高温
                "feels_like": f.temp_min,  # 复用字段存日最低温
                "humidity": None,
                "pressure": None,
                "wind_speed": f.wind_speed_max,
                "wind_direction": None,
                "weather_code": f.weather_code,
                "weather_desc": f.weather_desc,
                "precipitation": f.precipitation_sum,
                "visibility": None,
                "is_forecast": True,
                "raw": {"daily": {"sunrise": f.sunrise, "sunset": f.sunset}},
            }
        )

    # upsert：TimescaleDB 超表主键 (time, location_code)
    stmt = pg_insert(WeatherHistory).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["time", "location_code"],
        set_={
            "temperature": stmt.excluded.temperature,
            "feels_like": stmt.excluded.feels_like,
            "humidity": stmt.excluded.humidity,
            "pressure": stmt.excluded.pressure,
            "wind_speed": stmt.excluded.wind_speed,
            "wind_direction": stmt.excluded.wind_direction,
            "weather_code": stmt.excluded.weather_code,
            "weather_desc": stmt.excluded.weather_desc,
            "precipitation": stmt.excluded.precipitation,
            "visibility": stmt.excluded.visibility,
            "is_forecast": stmt.excluded.is_forecast,
            "raw": stmt.excluded.raw,
        },
    )
    await db.execute(stmt)


async def get_latest(location_code: str = "gz") -> WeatherHistory | None:
    """读取最新一条实测数据。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(WeatherHistory)
            .where(WeatherHistory.location_code == location_code)
            .where(WeatherHistory.is_forecast.is_(False))
            .order_by(WeatherHistory.time.desc())
            .limit(1)
        )
        return await db.scalar(stmt)


async def list_recent(location_code: str = "gz", limit: int = 24) -> list[WeatherHistory]:
    """读取最近 N 条实测数据（默认 24 条）。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(WeatherHistory)
            .where(WeatherHistory.location_code == location_code)
            .where(WeatherHistory.is_forecast.is_(False))
            .order_by(WeatherHistory.time.desc())
            .limit(limit)
        )
        result = await db.scalars(stmt)
        return list(result)


async def list_forecast(location_code: str = "gz") -> list[WeatherHistory]:
    """读取 7 天预报行。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(WeatherHistory)
            .where(WeatherHistory.location_code == location_code)
            .where(WeatherHistory.is_forecast.is_(True))
            .order_by(WeatherHistory.time.asc())
        )
        result = await db.scalars(stmt)
        return list(result)
