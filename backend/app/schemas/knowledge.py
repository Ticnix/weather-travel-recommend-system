"""RAG 知识库模块 Schema。"""

from typing import Optional

from pydantic import BaseModel


class IndexResult(BaseModel):
    documents: int
    chunks: int
    stored: int
    total_in_db: int
    embedding_mode: str


class SearchHit(BaseModel):
    title: str
    source: str
    content: str
    chunk_index: int
    similarity: float


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = None
