from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class News(Base, TimestampMixin):
    """资讯 / 公告表。"""

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 原文正文：采集类资讯抓取到的正文（有值时详情页直接渲染，无需依赖 iframe 内嵌）
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 原文链接：采集类资讯（如中央气象台预警）用于详情页内嵌展示原文
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(
        String(32), default="news", nullable=False
    )  # news / notice / alert
    author: Mapped[str | None] = mapped_column(String(64), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_top: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<News id={self.id} title={self.title}>"
