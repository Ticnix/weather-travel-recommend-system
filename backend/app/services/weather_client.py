"""气象数据源客户端：对接 Open-Meteo（免费免 Key）。

提供三类能力：
- 实时天气（current）
- 7 天预报（daily）
- 简易预警（Open-Meteo 对中国无官方预警 API，按降水量/风速阈值兜底生成）

广州默认坐标 23.13°N, 113.26°E。
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings

# WMO 天气编码 → 中文描述（Open-Meteo 采用 WMO code）
WMO_CODE_DESC: dict[int, str] = {
    0: "晴",
    1: "多云",
    2: "阴",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小雨",
    53: "小雨",
    55: "中雨",
    56: "冻雨",
    57: "冻雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "霰",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "强雷阵雨伴冰雹",
}

# 风向角度 → 八方位
_WIND_DIRS = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]


def _wind_dir(deg: float | None) -> str | None:
    if deg is None:
        return None
    return _WIND_DIRS[int((deg + 22.5) // 45) % 8]


@dataclass
class CurrentWeather:
    time: datetime
    temperature: float | None
    feels_like: float | None
    humidity: float | None
    pressure: float | None
    wind_speed: float | None
    wind_direction: str | None
    weather_code: str | None
    weather_desc: str | None
    precipitation: float | None
    visibility: float | None  # Open-Meteo 返回 m，这里转 km
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyForecast:
    date: str  # YYYY-MM-DD
    temp_max: float | None
    temp_min: float | None
    precipitation_sum: float | None
    wind_speed_max: float | None
    weather_code: str | None
    weather_desc: str | None
    sunrise: str | None
    sunset: str | None
    is_forecast: bool = True  # True=未来预报 / False=过去实测(历史回补)


@dataclass
class WeatherAlert:
    level: str  # info / warn / danger
    type: str  # rain / wind / ...
    title: str
    detail: str


@dataclass
class WeatherBundle:
    """一次拉取的完整气象数据包。"""

    current: CurrentWeather
    daily: list[DailyForecast]
    alerts: list[WeatherAlert]
    location_code: str


class WeatherClient:
    """Open-Meteo 客户端。"""

    def __init__(self, base_url: str | None = None, timeout: float = 15.0) -> None:
        self.base_url = base_url or settings.WEATHER_API_BASE
        self.timeout = timeout

    async def fetch(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        location_code: str | None = None,
        past_days: int = 0,
    ) -> WeatherBundle:
        """一次性拉取实时 +（过去 past_days 天）+ 未来 7 天预报 + 衍生预警。

        past_days>0 时，Open-Meteo 会在 daily 数组前面返回过去 N 天的日统计，
        用于回补历史天气（作为实测写入时序表）。
        """
        lat = latitude if latitude is not None else settings.DEFAULT_LATITUDE
        lon = longitude if longitude is not None else settings.DEFAULT_LONGITUDE
        loc = location_code or settings.DEFAULT_CITY_CODE

        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "Asia/Shanghai",
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m,wind_direction_10m,"
                "surface_pressure,precipitation,visibility"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,wind_speed_10m_max,sunrise,sunset"
            ),
            "forecast_days": 7,
            "past_days": max(0, min(past_days, 92)),
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}/forecast", params=params)
            resp.raise_for_status()
            data = resp.json()

        current = self._parse_current(data.get("current", {}))
        daily = self._parse_daily(data.get("daily", {}))
        alerts = self._derive_alerts(current, daily)

        return WeatherBundle(current=current, daily=daily, alerts=alerts, location_code=loc)

    @staticmethod
    def _parse_current(c: dict[str, Any]) -> CurrentWeather:
        wmo = c.get("weather_code")
        desc = WMO_CODE_DESC.get(wmo) if wmo is not None else None
        vis_m = c.get("visibility")
        return CurrentWeather(
            time=_parse_dt(c.get("time")),
            temperature=c.get("temperature_2m"),
            feels_like=c.get("apparent_temperature"),
            humidity=c.get("relative_humidity_2m"),
            pressure=c.get("surface_pressure"),
            wind_speed=c.get("wind_speed_10m"),
            wind_direction=_wind_dir(c.get("wind_direction_10m")),
            weather_code=str(wmo) if wmo is not None else None,
            weather_desc=desc,
            precipitation=c.get("precipitation"),
            visibility=(vis_m / 1000.0) if vis_m is not None else None,
            raw=c,
        )

    @staticmethod
    def _parse_daily(d: dict[str, Any]) -> list[DailyForecast]:
        from datetime import date as _date

        dates = d.get("time", [])
        out: list[DailyForecast] = []
        today_str = _date.today().isoformat()
        for i, date in enumerate(dates):
            wmo = _idx(d.get("weather_code"), i)
            # 日期 <= 今天 视为「实测/历史」，> 今天 视为「预报」
            is_forecast = date > today_str
            out.append(
                DailyForecast(
                    date=date,
                    temp_max=_idx(d.get("temperature_2m_max"), i),
                    temp_min=_idx(d.get("temperature_2m_min"), i),
                    precipitation_sum=_idx(d.get("precipitation_sum"), i),
                    wind_speed_max=_idx(d.get("wind_speed_10m_max"), i),
                    weather_code=str(wmo) if wmo is not None else None,
                    weather_desc=WMO_CODE_DESC.get(wmo) if wmo is not None else None,
                    sunrise=_idx(d.get("sunrise"), i),
                    sunset=_idx(d.get("sunset"), i),
                    is_forecast=is_forecast,
                )
            )
        return out

    @staticmethod
    def _derive_alerts(current: CurrentWeather, daily: list[DailyForecast]) -> list[WeatherAlert]:
        """按阈值生成简易预警（Open-Meteo 对中国无官方预警 API）。"""
        alerts: list[WeatherAlert] = []
        # 当下风速
        if current.wind_speed is not None and current.wind_speed >= settings.WIND_ALERT_KMH:
            alerts.append(
                WeatherAlert(
                    level="warn",
                    type="wind",
                    title="大风提示",
                    detail=f"当前风速 {current.wind_speed:.1f} km/h，注意出行安全",
                )
            )
        # 未来 24h 降水（取首日预报）
        if daily:
            rain = daily[0].precipitation_sum or 0
            if rain >= settings.RAIN_ALERT_MM:
                level = "danger" if rain >= 25 else "warn"
                alerts.append(
                    WeatherAlert(
                        level=level,
                        type="rain",
                        title="强降水提示" if level == "danger" else "降水提示",
                        detail=f"未来 24h 降水量 {rain:.1f} mm，注意防雨防涝",
                    )
                )
        return alerts


def _idx(arr: list[Any] | None, i: int) -> Any:
    if not arr or i >= len(arr):
        return None
    return arr[i]


def _parse_dt(s: str | None) -> datetime:
    """Open-Meteo current.time 形如 '2026-08-23T18:15'，无时区后缀，按 Asia/Shanghai 解析后转 UTC。"""
    if not s:
        return datetime.now(UTC)
    # 用 fromisoformat 解析 naive，再附加时区
    try:
        from datetime import datetime as _dt

        naive = _dt.fromisoformat(s)
        from zoneinfo import ZoneInfo

        return naive.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(UTC)
    except Exception:  # noqa: BLE001 时间解析失败兜底为当前时间，避免接口整体失败
        return datetime.now(UTC)


# 默认单例
weather_client = WeatherClient()
