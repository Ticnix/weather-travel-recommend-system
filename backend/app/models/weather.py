from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeatherHistory(Base):
    """气象时序表（TimescaleDB 超表，按 time 分区）。

    注意：该表不使用通用 TimestampMixin，因为时间主键列即业务时间。
    复合主键 (time, location_code)，time 为分区列。
    """

    __tablename__ = "weather_history"

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    location_code: Mapped[str] = mapped_column(
        String(32), primary_key=True, nullable=False
    )  # 城市/站点代码，如 gz
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)  # 气温 ℃
    feels_like: Mapped[float | None] = mapped_column(Float, nullable=True)  # 体感温度 ℃
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)  # 相对湿度 %
    pressure: Mapped[float | None] = mapped_column(Float, nullable=True)  # 气压 hPa
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # 风速 km/h
    wind_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 风向
    weather_code: Mapped[str | None] = mapped_column(
        String(16), nullable=True, index=True
    )  # 天气编码
    weather_desc: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 天气描述
    precipitation: Mapped[float | None] = mapped_column(Float, nullable=True)  # 降水量 mm
    visibility: Mapped[float | None] = mapped_column(Float, nullable=True)  # 能见度 km
    is_forecast: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # 预报 or 实测
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 原始数据

    def __repr__(self) -> str:
        return f"<WeatherHistory time={self.time} loc={self.location_code}>"
