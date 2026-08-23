from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KnowledgeChunk(Base, TimestampMixin):
    """知识库向量表（RAG 检索）。

    关键约束：embedding 维度固定为 1024，模型使用智谱 embedding-3（dimensions=1024）。
    (source, chunk_index) 唯一，用于重复建索引时的 upsert 去重。
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("source", "chunk_index", name="uq_knowledge_source_chunk"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 来源文档/URL
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 文本切片
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 文档内分块序号
    embedding: Mapped[list | None] = mapped_column(Vector(1024), nullable=True)  # 1024 维向量
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 额外元数据

    def __repr__(self) -> str:
        return f"<KnowledgeChunk id={self.id} title={self.title}>"
