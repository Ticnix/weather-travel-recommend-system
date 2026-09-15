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

from app.core.config import settings
from app.services.city_dict import lookup_city
from app.services.qweather_client import QWeatherClient, WeatherBundle
from app.services.weather_client import WeatherClient

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
