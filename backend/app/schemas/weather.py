"""气象模块 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CurrentWeatherOut(BaseModel):
    time: datetime
    temperature: float | None = None
    feels_like: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    wind_speed: float | None = None
    wind_direction: str | None = None
    weather_code: str | None = None
    weather_desc: str | None = None
    precipitation: float | None = None
    visibility: float | None = None


class ForecastOut(BaseModel):
    time: datetime
    temp_max: float | None = None
    temp_min: float | None = None
    precipitation_sum: float | None = None
    wind_speed_max: float | None = None
    weather_code: str | None = None
    weather_desc: str | None = None


class WeatherHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: datetime
    location_code: str
    temperature: float | None = None
    feels_like: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    wind_speed: float | None = None
    wind_direction: str | None = None
    weather_code: str | None = None
    weather_desc: str | None = None
    precipitation: float | None = None
    visibility: float | None = None
    is_forecast: bool


class SyncResult(BaseModel):
    ok: bool
    location: str | None = None
    temperature: float | None = None
    weather_desc: str | None = None
    alerts: int = 0
    daily: int = 0
    error: str | None = None
