"""用户私有知识库向量表（多租户 RAG）。

用户上传自己的出行计划、旅游攻略、旅行笔记等文档，切块向量化后存入本表，
通过 user_id 隔离，检索时只查当前用户自己的内容。

与公共知识库（knowledge_chunks）分离，避免数据串扰。
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserKnowledge(Base, TimestampMixin):
    """用户私有知识库表。"""

    __tablename__ = "user_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # 文档/计划标题
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 来源（文件名/类型）
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 文本切片
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(1024), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<UserKnowledge id={self.id} user_id={self.user_id} title={self.title}>"
