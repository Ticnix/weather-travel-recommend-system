"""气象数据同步服务：把 WeatherBundle 写入 weather_history 时序表。

- 实时数据 → is_forecast=False 的一行
- 7 天预报 → is_forecast=True 的 7 行
- 预警暂不入库，由接口实时返回（后续可建 alerts 表）
"""

from datetime import UTC, datetime

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
    past_days: int = 0,
) -> WeatherBundle:
    """拉取气象数据并写入时序表，返回原始数据包。

    past_days>0 时回补过去 N 天日统计作为实测写入（历史天气）。
    use_celery_engine=True 时使用独立的 NullPool 引擎，避免 Celery 跨 asyncio.run 复用连接池出错。
    """
    bundle = await weather_client.fetch(latitude, longitude, location_code, past_days=past_days)
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

    # 日预报 / 历史实测行（past_days>0 时含过去 daily）
    for f in bundle.daily:
        # 用日期 + 00:00:00Z 作为日时间戳，便于按天去重
        try:
            day = datetime.strptime(f.date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        rows.append(
            {
                "time": day,
                "location_code": bundle.location_code,
                "temperature": f.temp_max,  # 日最高温
                "feels_like": f.temp_min,  # 日最低温
                "humidity": None,
                "pressure": None,
                "wind_speed": f.wind_speed_max,
                "wind_direction": None,
                "weather_code": f.weather_code,
                "weather_desc": f.weather_desc,
                "precipitation": f.precipitation_sum,
                "visibility": None,
                # 过去日期(is_forecast=False)作为实测入库，未来作为预报
                "is_forecast": f.is_forecast,
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


async def page_records(
    location_code: str = "gz",
    page: int = 1,
    page_size: int = 20,
    date_from: str | None = None,
    date_to: str | None = None,
    weather_desc: str | None = None,
    forecast: bool | None = None,
) -> tuple[list[WeatherHistory], int]:
    """管理端气象时序分页查询。

    支持：分页、按日期范围(date_from~date_to, YYYY-MM-DD)、天气描述关键字、
    是否预报(forecast)过滤。返回 (rows, total)。
    """
    from sqlalchemy import func

    async with AsyncSessionLocal() as db:
        conditions = [WeatherHistory.location_code == location_code]
        if date_from:
            try:
                fd = datetime.fromisoformat(date_from)
                conditions.append(WeatherHistory.time >= fd)
            except ValueError:
                pass
        if date_to:
            try:
                td = datetime.fromisoformat(date_to).replace(
                    hour=23, minute=59, second=59, microsecond=0
                )
                conditions.append(WeatherHistory.time <= td)
            except ValueError:
                pass
        if weather_desc:
            conditions.append(WeatherHistory.weather_desc.ilike(f"%{weather_desc}%"))
        if forecast is not None:
            conditions.append(WeatherHistory.is_forecast.is_(forecast))

        total = (
            await db.scalar(select(func.count()).select_from(WeatherHistory).where(*conditions))
            or 0
        )

        stmt = (
            select(WeatherHistory)
            .where(*conditions)
            .order_by(WeatherHistory.time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.scalars(stmt)
        return list(result), int(total)


async def agg_daily(
    location_code: str = "gz",
    days: int = 30,
    metrics: tuple[str, ...] = ("temperature", "humidity", "precipitation"),
) -> list[dict]:
    """按天聚合气象指标均值（管理端时序统计用）。

    返回 [{date: 'YYYY-MM-DD', temperature_avg, humidity_avg, precipitation_avg, ...}]。
    """
    from sqlalchemy import Date, cast, func

    async with AsyncSessionLocal() as db:
        from datetime import timedelta

        since = datetime.now(UTC) - timedelta(days=days)
        # 聚合表达式
        aggs = {f"{m}_avg": func.avg(getattr(WeatherHistory, m)) for m in metrics}
        stmt = (
            select(
                cast(WeatherHistory.time, Date).label("date"),
                *aggs.values(),
            )
            .where(WeatherHistory.location_code == location_code)
            .where(WeatherHistory.time >= since)
            .where(WeatherHistory.is_forecast.is_(False))
            .group_by(cast(WeatherHistory.time, Date))
            .order_by(cast(WeatherHistory.time, Date).asc())
        )
        rows = await db.execute(stmt)
        cols = ["date", *aggs.keys()]
        # strict=True：列名与查询结果的列数必须一致，
        # 不一致说明 SQL 改了但 cols 没同步——这种错必须当场炸，不能静默少字段
        return [dict(zip(cols, row, strict=True)) for row in rows.all()]
