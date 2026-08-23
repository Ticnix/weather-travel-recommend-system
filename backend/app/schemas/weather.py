"""气象模块 Schema。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class CurrentWeatherOut(BaseModel):
    time: datetime
    temperature: Optional[float] = None
    feels_like: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[str] = None
    weather_code: Optional[str] = None
    weather_desc: Optional[str] = None
    precipitation: Optional[float] = None
    visibility: Optional[float] = None


class ForecastOut(BaseModel):
    time: datetime
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    precipitation_sum: Optional[float] = None
    wind_speed_max: Optional[float] = None
    weather_code: Optional[str] = None
    weather_desc: Optional[str] = None


class WeatherHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: datetime
    location_code: str
    temperature: Optional[float] = None
    feels_like: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[str] = None
    weather_code: Optional[str] = None
    weather_desc: Optional[str] = None
    precipitation: Optional[float] = None
    visibility: Optional[float] = None
    is_forecast: bool


class SyncResult(BaseModel):
    ok: bool
    location: Optional[str] = None
    temperature: Optional[float] = None
    weather_desc: Optional[str] = None
    alerts: int = 0
    daily: int = 0
    error: Optional[str] = None
