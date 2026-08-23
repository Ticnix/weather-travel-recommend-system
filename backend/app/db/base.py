from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""

    pass


class TimestampMixin:
    """通用时间戳字段。

    同时设置 Python 侧 default/onupdate 与 server_default：
    - Python 侧值在 insert/update 时写入对象内存，避免 Pydantic 序列化触发异步懒加载（greenlet 错误）
    - server_default 作为数据库兜底
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
