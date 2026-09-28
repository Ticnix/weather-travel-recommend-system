"""区级天气：把「用户在哪」翻译成「哪里的天气」。

为什么单独一层，而不是改 /weather/current：
那个接口读的是按 location_code 落库的时序数据，管理端的统计、历史、连续聚合
都挂在它上面，且只有 Celery 定时同步过的点才有数据。而区级天气是**按需产生**的——
用户第一次打开某个区才去取。混进原接口会让"统计到底统计了哪些点"说不清。

这里把四件事串起来：
1. 解析位置：区名（「南沙区」）或经纬度（浏览器定位）→ 统一的 (city, district, lat, lon)
2. 取数：网格数据源按坐标取，坐标越准越贴近"我这个区"
3. 落库：用区名当 location_code 写入时序表，区级数据同样能进历史/聚合
4. 缓存：同一个区 10 分钟内不重复打上游

关于「为什么坐标取数走 Open-Meteo 而不是和风」：和风要先做 geo 查表拿 LocationID，
而网格数据源的原生输入就是经纬度，坐标请求用它更直接；城市级仍按 WEATHER_PROVIDER 配置走原链路。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.core.cache import cached
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services import amap_client, district_dict, weather_sync
from app.services.city_dict import lookup_city

# 注意：weather_client 是模块里的**单例实例**，不是模块本身——
# `from app.services import weather_client` 拿到的是模块，调用 .fetch() 会报 AttributeError
from app.services.weather_client import weather_client

logger = logging.getLogger(__name__)

# 区级天气 10 分钟缓存：实时天气本身是分钟级更新的，
# 但对"我这个区现在几度"来说 10 分钟足够，且能挡住刷新页面的重复请求
LOCAL_CACHE_TTL = 600


@dataclass
class ResolvedLocation:
    """解析后的位置：既是取数依据，也是要显示给用户看的"依据说明"。"""

    city: str
    district: str | None
    lat: float
    lon: float
    source: str  # geo=浏览器定位 / manual=手动选 / city=只有城市
    precision: str  # district=区级 / city=市中心（必须让用户知道差在哪）

    @property
    def location_code(self) -> str:
        """写库/缓存用的键：有区用区名（「南沙区」），否则用城市名。"""
        return self.district or self.city

    def as_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "district": self.district,
            "lat": round(self.lat, 4),
            "lon": round(self.lon, 4),
            "source": self.source,
            "precision": self.precision,
            "label": f"{self.city}市 · {self.district}" if self.district else self.city,
            "location_code": self.location_code,
        }


def _city_center(city: str) -> tuple[str, float, float]:
    """城市中心坐标（city_dict 未收录时回落默认城市）。"""
    info = lookup_city(city)
    if info is None:
        default = lookup_city(settings.AMAP_DEFAULT_CITY)
        if default is not None:
            return default.name, default.lat, default.lon
        return city, settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE
    return info.name, info.lat, info.lon


async def resolve(
    district: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> ResolvedLocation:
    """确定"用户的天气该按哪个点取"。

    优先级：经纬度（最准）> 区名 > 城市中心。
    任何一步失败都往下退一级，但**退级后 precision 会变成 city**——
    这样前端才能如实告诉用户"现在显示的是市中心的数据"，
    而不是让用户以为这就是他家门口的天气。
    """
    # 1) 浏览器定位给的经纬度：逆地理编码拿到区名，用户才看得懂"这是南沙区"
    if lat is not None and lon is not None:
        info = await amap_client.regeo(lat, lon)
        if info:
            raw_city = (info.get("city") or "").removesuffix("市")
            district_name = district_dict.canonical_district(info.get("district") or "")
            city = raw_city or settings.AMAP_DEFAULT_CITY
            if district_name:
                # 用区中心坐标而不是用户精确坐标：缓存命中率高，也更贴合"这个区的天气"
                coords = district_dict.district_coords(district_name)
                if coords:
                    return ResolvedLocation(city, district_name, coords[0], coords[1], "geo", "district")
            return ResolvedLocation(city, None, lat, lon, "geo", "city")
        # 逆地理编码不可用（无 Key / 上游挂了）：仍然用坐标取数，只是名字说不出来
        return ResolvedLocation(
            settings.AMAP_DEFAULT_CITY, None, lat, lon, "geo", "city"
        )

    # 2) 手动选择的区名
    if district:
        name = district_dict.canonical_district(district) or district
        owners = district_dict.cities_of(name)
        city = owners[0] if owners else settings.AMAP_DEFAULT_CITY
        coords = district_dict.district_coords(name)
        if coords:
            return ResolvedLocation(city, name, coords[0], coords[1], "manual", "district")
        city_name, clat, clon = _city_center(city)
        return ResolvedLocation(city_name, None, clat, clon, "manual", "city")

    # 3) 什么都没给：城市中心
    city_name, clat, clon = _city_center(settings.AMAP_DEFAULT_CITY)
    return ResolvedLocation(city_name, None, clat, clon, "city", "city")


def _serialize(bundle: Any) -> dict[str, Any]:
    """统一成前端既有的字段名（current / forecast），前端可直接复用现有类型。

    **不含 location**：缓存只存天气本身。位置信息每次按当前这次请求重新算，
    否则"坐标定位"的请求会拿到上一次"手动选南沙"缓存里的 source，
    前端就会把依据显示成错的。
    """
    c = bundle.current
    return {
        "current": {
            "location_code": bundle.location_code,
            "temperature": c.temperature,
            "feels_like": c.feels_like,
            "humidity": c.humidity,
            "wind_speed": c.wind_speed,
            "wind_direction": c.wind_direction,
            "weather_code": c.weather_code,
            "weather_desc": c.weather_desc,
            "precipitation": c.precipitation,
            "visibility": c.visibility,
            "time": c.time.isoformat() if c.time else None,
        },
        "forecast": [
            {
                "date": d.date,
                "temp_max": d.temp_max,
                "temp_min": d.temp_min,
                "weather_desc": d.weather_desc,
                "weather_code": d.weather_code,
                "precipitation": d.precipitation_sum,
                "wind_speed": d.wind_speed_max,
                "is_forecast": d.is_forecast,
            }
            for d in bundle.daily
        ],
    }


async def _fetch_with_retry(loc: ResolvedLocation, attempts: int = 2) -> Any:
    """按坐标取数，偶发失败自动重试。

    **为什么必须重试**：实测同一批请求里会零散失败一两条（`httpx.ConnectError`，
    且它的 str() 是空的，看起来像"什么错都没说"）。单次抖动就让用户看到
    "当地天气没取到"是不可接受的——重试一次的代价只是几百毫秒，成功率却高得多。
    """
    last_exc: Exception | None = None
    for index in range(attempts):
        try:
            return await weather_client.fetch(
                latitude=loc.lat, longitude=loc.lon, location_code=loc.location_code
            )
        except Exception as exc:  # noqa: BLE001 上游任何异常都按"可重试"处理
            last_exc = exc
            logger.warning(
                "区级天气取数失败（第 %s/%s 次）location=%s type=%s msg=%r",
                index + 1,
                attempts,
                loc.location_code,
                type(exc).__name__,
                str(exc),
            )
            if index + 1 < attempts:
                await asyncio.sleep(0.4)
    assert last_exc is not None
    raise last_exc


async def get_local_weather(
    district: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """取"用户所在区"的实时天气 + 7 天预报。"""
    loc = await resolve(district=district, lat=lat, lon=lon)
    cache_key = f"weather:local:{loc.location_code}"

    async def _load() -> dict[str, Any]:
        bundle = await _fetch_with_retry(loc)
        # 落库：区级数据也进时序表（管理端/历史/聚合都能看到这个区）
        # 落库失败不影响本次展示——用户要的是天气，不是入库成功
        try:
            async with AsyncSessionLocal() as db:
                await weather_sync.store_weather(db, bundle)
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("区级天气落库失败 location=%s: %s", loc.location_code, exc)
        return _serialize(bundle)

    payload = await cached(cache_key, LOCAL_CACHE_TTL, _load)
    # location 拼在缓存之外：它是"这次请求的解析结果"，不该被上一次的缓存覆盖
    return {"location": loc.as_dict(), **payload}


def list_districts(city: str) -> list[dict[str, Any]]:
    """某城市可选的区列表：带 has_coords 标记，前端据此说明"哪些区能精确到区"。"""
    items = []
    for name in district_dict.districts_of_city(city):
        items.append({"name": name, "has_coords": district_dict.district_coords(name) is not None})
    return items
