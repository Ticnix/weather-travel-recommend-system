"""用户偏好表（Day 55）。

**为什么是独立新表而不是 users 表加列**：本项目线上用 `create_all`，
它只会创建缺失的**表**，不会给已存在的表补**列**——
偏好项以后还会加，放 JSONB 里加键不用再写迁移。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserPreference(Base):
    """一行对应一个用户；具体键与含义见 `schemas/user_preference.py`。"""

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<UserPreference user={self.user_id}>"
