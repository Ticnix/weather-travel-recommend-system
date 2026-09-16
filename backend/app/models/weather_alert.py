"""天气预警记录表（Day 36）。

在此之前，预警是「接口实时返回、不入库」的——拿不到「这条预警我之前见过吗」
这个信息，也就无法做到「一发布就推送、且同一条不重复推」。本表把预警落库，
核心是 fingerprint 这个去重键。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WeatherAlert(Base, TimestampMixin):
    """一条天气预警记录（fingerprint 全局唯一）。"""

    __tablename__ = "weather_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 去重键 = city|level|title 的短哈希。
    # 上游（和风）每次轮询都返回「当前生效的全部预警」，用它与库比对：
    # 命中 → 老预警（只刷新 last_seen_at）；未命中 → 新发布的预警（要推送）。
    fingerprint: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    city: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # info / warn / danger
    type: Mapped[str] = mapped_column(String(32), default="", nullable=False)  # rain / wind ...
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 首次 / 最近一次在上游看到的时间：可据此判断预警是否已解除
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 推送情况：为空表示尚未推送（新预警但没匹配到用户）
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<WeatherAlert {self.city} {self.level} {self.title}>"
