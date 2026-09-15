"""行程笔记表（用户自由撰写的 Markdown 文档）。

与 itineraries 的区别：
- itineraries：**结构化**行程（日期/时间/地点/活动），用于精确匹配「某天某时某地做什么」，
  从而结合天气生成出行提醒；
- trip_notes：**自由格式**的长文笔记（攻略、清单、备忘），支持 Markdown 编辑、
  文件导入与导出，适合写"三天两夜怎么玩"这类内容。
"""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TripNote(Base, TimestampMixin):
    """用户行程笔记。"""

    __tablename__ = "trip_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")  # Markdown 正文
    note_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD（可空）
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 关联地点（可空）

    def __repr__(self) -> str:
        return f"<TripNote id={self.id} title={self.title}>"
