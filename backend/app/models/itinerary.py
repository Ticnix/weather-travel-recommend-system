"""用户行程表（结构化存储，用于行程天气提醒）。

与用户私有知识库（user_knowledge，纯文本分块）不同，本表存「结构化行程」，
字段含日期/时间/地点/活动类型，便于精确匹配「某天某时某地做什么」，
从而结合当天天气生成出行提醒与推荐。
"""

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Itinerary(Base, TimestampMixin):
    """用户行程条目。"""

    __tablename__ = "itineraries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # 行程标题，如"白云山爬山"
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 地点
    activity: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 活动类型（爬山/夜游/逛街等）
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 备注

    def __repr__(self) -> str:
        return f"<Itinerary id={self.id} date={self.date} title={self.title}>"