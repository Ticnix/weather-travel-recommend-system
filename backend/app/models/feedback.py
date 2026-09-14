from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Feedback(Base, TimestampMixin):
    """用户反馈表。"""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True
    )  # pending / processing / resolved / closed
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)  # 管理员回复
    # 必须显式声明 timezone=True：否则会被推断为 naive 时间，
    # 与代码里写入的 datetime.now(timezone.utc) 冲突（asyncpg 报 naive/aware 不匹配）
    reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # 回复时间

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} status={self.status}>"
