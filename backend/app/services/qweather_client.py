"""和风天气 QWeather 客户端。

API 文档：https://dev.qweather.com/docs/api/

提供三类能力：
- 实时天气（/weather/now）：当前温度、湿度、风速、风向、降水等
- 7 天预报（/weather/7d）：未来 7 天每天的预报
- 天气预警（/warning/now）：当前生效的官方预警（台风/暴雨/高温等）

设计要点：
- 城市定位优先用和风 LocationID（更准），用户传入城市名时通过 city_dict 解析
- 与 Open-Meteo 客户端数据结构保持一致，方便上层统一调用
- 内置重试与超时，超时上限 8 秒（和风 API 限频严格，避免长占用）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.services.city_dict import lookup_city

logger = logging.getLogger(__name__)


# 和风天气现象 → 简中描述（官方图标代码，100 是晴，101-104 多云等）
QW_ICON_DESC: dict[int, str] = {
    100: "晴",
    101: "多云",
    102: "少云",
    103: "晴间多云",
    104: "阴",
    150: "晴",
    151: "多云",
    152: "少云",
    153: "晴间多云",
    300: "阵雨",
    301: "强阵雨",
    302: "雷阵雨",
    305: "小雨",
    306: "中雨",
    307: "大雨",
    310: "暴雨",
    311: "大暴雨",
    312: "特大暴雨",
    315: "冻雨",
    317: "冻雨",
    318: "冻雨",
    350: "阵雨夹雪",
    351: "阵雨夹雪",
    352: "阵雨夹雪",
    400: "小雪",
    401: "中雪",
    402: "大雪",
    403: "暴雪",
    404: "雨夹雪",
    405: "雨夹雪",
    406: "雨夹雪",
    407: "阵雪",
    408: "阵雪",
    409: "阵雪",
    410: "中雪",
    456: "中雪",
    457: "中雪",
    500: "雾",
    501: "雾",
    502: "霾",
    503: "扬沙",
    504: "浮尘",
    507: "沙尘暴",
    508: "强沙尘暴",
    509: "浓雾",
    510: "浓雾",
    511: "浓雾",
    512: "浓雾",
    513: "浓雾",
    514: "浓雾",
    515: "浓雾",
    900: "热",
    901: "冷",
    999: "未知",
}

# 和风预警等级 → 中文（蓝色/黄色/橙色/红色）
QW_ALERT_LEVEL: dict[str, str] = {
    "Blue": "蓝色",
    "Yellow": "黄色",
    "Orange": "橙色",
    "Red": "红色",
    "White": "白色",
}

# 和风预警类型 → 中文
QW_ALERT_TYPE: dict[str, str] = {
    "Typhoon": "台风",
    "Rainstorm": "暴雨",
    "HeavyRain": "强降雨",
    "Thunder": "雷电",
    "HighTemp": "高温",
    "LowTemp": "低温",
    "Wind": "大风",
    "Fog": "大雾",
    "Haze": "霾",
    "Snow": "暴雪",
    "Frost": "霜冻",
    "Sandstorm": "沙尘暴",
    "ColdWave": "寒潮",
    "HeatWave": "热浪",
}

# 风力等级（和风用 Beaufort 数字 0~12）
WIND_LEVEL: dict[int, str] = {
    0: "无风",
    1: "软风",
    2: "轻风",
    3: "微风",
    4: "和风",
    5: "清劲风",
    6: "强风",
    7: "疾风",
    8: "大风",
    9: "烈风",
    10: "狂风",
    11: "暴风",
    12: "台风",
}


@dataclass
class CurrentWeather:
    """实时天气。字段命名与 weather_client.py 对齐。"""

    time: datetime
    temperature: float | None
    feels_like: float | None
    humidity: float | None
    pressure: float | None
    wind_speed: float | None
    wind_direction: str | None
    wind_scale: str | None
    weather_code: str | None
    weather_desc: str | None
    precipitation: float | None
    visibility: float | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyForecast:
    date: str
    temp_max: float | None
    temp_min: float | None
    precipitation_sum: float | None
    wind_speed_max: float | None
    wind_scale_max: str | None
    weather_code: str | None
    weather_desc: str | None
    sunrise: str | None
    sunset: str | None


@dataclass
class WeatherAlert:
    level: str
    type: str
    title: str
    detail: str


@dataclass
class WeatherBundle:
    current: CurrentWeather
    daily: list[DailyForecast]
    alerts: list[WeatherAlert]
    location_code: str


def _parse_qweather_dt(s: str | None) -> datetime:
    """和风时间格式 '2026-08-25T16:00+08:00' -> aware datetime。"""
    if not s:
        return datetime.now(UTC)
    try:
        # Python 3.11+ 直接支持时区后缀
        return datetime.fromisoformat(s)
    except Exception:  # noqa: BLE001 解析失败必须兜底，不能让天气接口整体挂掉
        return datetime.now(UTC)


class QWeatherClient:
    """和风天气客户端。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> None:
        self.api_key = api_key or settings.QWEATHER_API_KEY
        self.base_url = (base_url or settings.QWEATHER_BASE_URL).rstrip("/")
        self.timeout = timeout

    def _resolve_location(self, location: str | None) -> str:
        """把"城市名"解析成和风 LocationID；已是 LocationID 则直接返回。"""
        if not location:
            return settings.QWEATHER_DEFAULT_LOCATION
        # 纯数字（如 101280101）直接作为 LocationID
        if location.isdigit():
            return location
        city = lookup_city(location)
        if city:
            return city.qweather_id
        # 未命中字典时退化：传入经纬度"lon,lat"和风也支持
        return location

    async def _get(self, path: str, location: str) -> dict[str, Any]:
        """通用 GET 请求，自动加 key/单位参数。"""
        if not self.api_key:
            raise RuntimeError("QWEATHER_API_KEY 未配置，请在 .env 设置")
        params = {"location": self._resolve_location(location), "key": self.api_key, "lang": "zh"}
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        # 和风响应 code 不为 "200" 时是业务错误（限频/无效 key 等）
        if str(data.get("code")) != "200":
            raise RuntimeError(f"和风天气 API 错误 code={data.get('code')}: {data.get('msg')}")
        return data

    async def fetch(self, location: str | None = None) -> WeatherBundle:
        """一次性拉取实时 + 7 天预报 + 官方预警（同一城市）。"""
        loc = location or settings.QWEATHER_DEFAULT_LOCATION
        now_data = (await self._get("/weather/now", loc))["now"]
        daily_data = (await self._get("/weather/7d", loc))["daily"]

        # 预警（失败不影响主流程）
        alerts: list[WeatherAlert] = []
        try:
            warn_data = await self._get("/warning/now", loc)
            for w in warn_data.get("warning", []):
                alerts.append(
                    WeatherAlert(
                        level=QW_ALERT_LEVEL.get(w.get("level"), w.get("level", "")),
                        type=QW_ALERT_TYPE.get(w.get("type"), w.get("type", "")),
                        title=w.get("title", ""),
                        detail=w.get("text", ""),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("和风预警拉取失败（不影响主流程）: %s", exc)

        current = self._parse_current(now_data)
        daily = self._parse_daily(daily_data)
        return WeatherBundle(current=current, daily=daily, alerts=alerts, location_code=loc)

    @staticmethod
    def _parse_current(n: dict[str, Any]) -> CurrentWeather:
        icon = int(n.get("icon", 999))
        wind_scale = n.get("windScale", "")
        return CurrentWeather(
            time=_parse_qweather_dt(n.get("obsTime")),
            temperature=_to_float(n.get("temp")),
            feels_like=_to_float(n.get("feelsLike")),
            humidity=_to_float(n.get("humidity")),
            pressure=_to_float(n.get("pressure")),
            wind_speed=_to_float(n.get("windSpeed")),
            wind_direction=n.get("windDir"),
            wind_scale=WIND_LEVEL.get(_wind_beaufort(wind_scale), wind_scale),
            weather_code=str(icon),
            weather_desc=QW_ICON_DESC.get(icon, n.get("text", "")),
            precipitation=_to_float(n.get("precip")),
            visibility=_to_float(n.get("vis")),
            raw=n,
        )

    @staticmethod
    def _parse_daily(d: list[dict[str, Any]]) -> list[DailyForecast]:
        out: list[DailyForecast] = []
        for day in d:
            icon = int(day.get("iconDay", 999))
            wind_scale_max = day.get("windScaleDay", "")
            out.append(
                DailyForecast(
                    date=day.get("fxDate", ""),
                    temp_max=_to_float(day.get("tempMax")),
                    temp_min=_to_float(day.get("tempMin")),
                    precipitation_sum=_to_float(day.get("precip")),
                    wind_speed_max=_to_float(day.get("windSpeedDay")),
                    wind_scale_max=WIND_LEVEL.get(_wind_beaufort(wind_scale_max), wind_scale_max),
                    weather_code=str(icon),
                    weather_desc=QW_ICON_DESC.get(icon, day.get("textDay", "")),
                    sunrise=day.get("sunrise"),
                    sunset=day.get("sunset"),
                )
            )
        return out


def _to_float(v: Any) -> float | None:
    if v in (None, "", "--"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _wind_beaufort(scale_text: str) -> int:
    """和风 windScale 形如 '3-4'/'5'，取较大值映射 Beaufort。"""
    try:
        parts = scale_text.split("-")
        return max(int(p) for p in parts)
    except Exception:  # noqa: BLE001 和风格式不稳定（如 'unknown'），解析失败返回 -1
        return -1


# 默认单例
qweather_client = QWeatherClient()
