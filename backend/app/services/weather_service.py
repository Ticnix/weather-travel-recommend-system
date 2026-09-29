"""统一天气服务层：根据 WEATHER_PROVIDER 配置路由到具体数据源。

支持的数据源：
- qweather   : 和风天气（国内本地化、官方预警，需 Key）
- open_meteo : Open-Meteo（免费免 Key，全球覆盖）

两个客户端的 WeatherBundle 结构已对齐，本层负责：
1. 按配置选择数据源实例
2. 城市名 → 经纬度/LocationID 的归一化处理
3. 数据源失败时的降级（和风挂了自动切 Open-Meteo）
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services.city_dict import lookup_city
from app.services.qweather_client import QWeatherClient, WeatherBundle
from app.services.weather_client import AirQuality, HourlyPoint, WeatherClient

logger = logging.getLogger(__name__)

_qweather = QWeatherClient()
_open_meteo = WeatherClient()


async def fetch_weather(city: str | None = None) -> WeatherBundle:
    """按配置拉取天气。城市名会先经 city_dict 解析。

    降级策略：配置为 qweather 但调用失败时，自动回退 Open-Meteo。
    """
    provider = settings.WEATHER_PROVIDER.lower()

    if provider == "qweather":
        try:
            return await _qweather.fetch(city)
        except Exception as exc:  # noqa: BLE001
            logger.warning("和风天气调用失败，降级到 Open-Meteo: %s", exc)
            return await _open_meteo_fetch(city)

    return await _open_meteo_fetch(city)


async def _open_meteo_fetch(city: str | None) -> WeatherBundle:
    """Open-Meteo 需要经纬度，城市名经 city_dict 解析。"""
    lat = lon = None
    loc_code = None
    if city:
        info = lookup_city(city)
        if info:
            lat, lon = info.lat, info.lon
            loc_code = info.name
    return await _open_meteo.fetch(latitude=lat, longitude=lon, location_code=loc_code)


async def fetch_hourly(city: str | None = None) -> list[HourlyPoint]:
    """逐小时预报。**主源：和风 /weather/24h**（免费档、国内直连稳定）；
    失败或未配和风 Key 时回退 Open-Meteo（境外源，本网络下时常被掐 TLS）。

    两条源在返回前归一化成同一种 HourlyPoint（路由/前端不感知差异）。
    """
    from datetime import datetime

    def _f(v: Any) -> float | None:
        try:
            return float(v) if v not in (None, "", "-") else None
        except (TypeError, ValueError):
            return None

    # --- 主源：和风 24h ---
    try:
        rows = await _qweather.fetch_hourly24(city)
        points: list[HourlyPoint] = []
        for r in rows:
            fx = (r.get("fxTime") or "").replace("+08:00", "")
            try:
                t = datetime.fromisoformat(fx)
            except ValueError:
                continue
            points.append(
                HourlyPoint(
                    time=t.replace(tzinfo=None) if t.tzinfo else t,
                    temperature=_f(r.get("temp")),
                    precip_prob=_f(r.get("pop")),
                    precip=_f(r.get("precip")),
                    weather_desc=(r.get("text") or None),
                    wind_speed=_f(r.get("windSpeed")),
                )
            )
        if points:
            return points
    except Exception as exc:  # noqa: BLE001 主源失败回退，不让逐小时板块整体 500
        logger.warning("和风逐小时失败，回退 Open-Meteo: %s", exc)

    # --- 备源：Open-Meteo ---
    bundle = await fetch_weather(city)
    # 用 getattr：和风路径的 WeatherBundle 没有 hourly 字段（两个客户端的
    # dataclass 形状不完全一致），直接取属性会在和风路径上 AttributeError
    hourly = getattr(bundle, "hourly", None)
    if hourly:
        return hourly
    fallback = await _open_meteo_fetch(city)
    return fallback.hourly


async def fetch_aqi(city: str | None = None) -> AirQuality:
    """当前空气质量（PM2.5 / PM10 / US AQI）。城市名经 city_dict 解析成坐标。"""
    lat = lon = None
    if city:
        info = lookup_city(city)
        if info:
            lat, lon = info.lat, info.lon
    return await _open_meteo.fetch_aqi(lat, lon)


async def fetch_alerts_with_fallback(city: str) -> list[Any]:
    """取某城市当前预警；主数据源没有预警时，用免费源兜底一次。

    为什么需要兜底：和风的 `/warning/now` 属于**付费能力**，免费 Key 调用会
    返回 403（实测），于是「配置为 qweather」时预警列表恒为空——
    预警推送功能等于从未启用。这里在主源没给出预警时，改用 Open-Meteo 的
    阈值规则（降水量/风速）补一次判断，保证功能在默认配置下就能跑起来。

    注意：阈值预警是「简易预警」而非官方预警，只作为兜底；
    等和风预警接口可用时，主源结果优先。
    """
    bundle = await fetch_weather(city)
    if bundle.alerts:
        return list(bundle.alerts)

    if settings.WEATHER_PROVIDER.lower() == "open_meteo":
        return []  # 主源就是免费源，没有就是真的没有

    try:
        fallback = await _open_meteo_fetch(city)
    except Exception as exc:  # noqa: BLE001 兜底失败就当作无预警，不影响主流程
        logger.warning("预警兜底源调用失败 %s: %s", city, exc)
        return []
    return list(fallback.alerts)


def weather_to_text(bundle: WeatherBundle) -> str:
    """把 WeatherBundle 转成结构化文本，供 LLM 阅读 / MCP 返回。"""
    c = bundle.current
    lines = [
        f"城市：{bundle.location_code or '默认'}",
        f"实时天气：{c.weather_desc or '未知'}，气温 {c.temperature}°C",
    ]
    if c.feels_like is not None:
        lines.append(f"体感温度 {c.feels_like}°C")
    if c.humidity is not None:
        lines.append(f"湿度 {c.humidity}%")
    if c.wind_direction:
        wind = c.wind_direction
        if getattr(c, "wind_scale", None):
            wind += f"（{c.wind_scale}）"
        lines.append(f"风向风力：{wind}")
    if c.precipitation is not None:
        lines.append(f"降水量 {c.precipitation}mm")
    if c.visibility is not None:
        lines.append(f"能见度 {c.visibility}km")

    lines.append("\n未来 7 天预报：")
    for d in bundle.daily:
        line = f"- {d.date}：{d.weather_desc or '未知'}，{d.temp_min}~{d.temp_max}°C"
        if d.precipitation_sum:
            line += f"，降水 {d.precipitation_sum}mm"
        lines.append(line)

    if bundle.alerts:
        lines.append("\n预警：")
        for a in bundle.alerts:
            lines.append(f"- [{a.level}] {a.title}：{a.detail}")

    return "\n".join(lines)
