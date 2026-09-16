"""生活指数时序表（Day 37）。

和风 /indices/1d 每天给出「当日」的各类指数（穿衣/紫外线/运动…），
接口本身不保留历史。要支持「这几天紫外线越来越强」这类对比，
必须自己按天存下来——所以这张表的主键是 (城市, 日期, 指数类型)。

同一天重复拉取走 upsert（同一格只保留最新一条），不会撑出重复行。
"""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LifeIndexRecord(Base, TimestampMixin):
    """某城市某天的某类生活指数。"""

    __tablename__ = "life_indices"
    __table_args__ = (
        UniqueConstraint("city", "date", "type_code", name="uq_life_indices_city_date_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)  # YYYY-MM-DD
    type_code: Mapped[str] = mapped_column(String(4), nullable=False)  # 和风指数编码
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # 穿衣指数
    level: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="", nullable=False)  # 炎热
    text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 官方建议文案

    def __repr__(self) -> str:
        return f"<LifeIndexRecord {self.city} {self.date} {self.name}={self.category}>"
