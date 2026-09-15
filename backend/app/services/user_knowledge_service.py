"""用户私有知识库服务（多租户 RAG）。

- add_document(): 用户上传文本 -> 分块 -> embedding -> 写入 user_knowledge 表
- search(): 限定 user_id 的向量语义检索

与公共知识库（rag_service）共用同一套分块器和 embedding 客户端，
仅存储表与检索范围不同（按 user_id 隔离）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.user_knowledge import UserKnowledge
from app.services.embedding_client import embedding_client
from app.services.knowledge_loader import split_text


async def add_document(
    user_id: int,
    title: str,
    content: str,
    source: str = "upload",
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """把用户上传的文本切块向量化后入库。

    Returns:
        {"chunks": int, "title": str}
    """
    if not content or not content.strip():
        raise ValueError("上传内容不能为空")

    chunks = split_text(content, 300, 50)
    if not chunks:
        raise ValueError("内容分块失败，请检查文档格式")

    # 批量生成向量
    vectors = await embedding_client.embed_texts(chunks)

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> int:
        rows = [
            UserKnowledge(
                user_id=user_id,
                title=title,
                source=source,
                content=c,
                chunk_index=i,
                embedding=vectors[i],
                meta={"scope": "user"},
            )
            for i, c in enumerate(chunks)
        ]
        s.add_all(rows)
        await s.commit()
        return len(rows)

    if owns_db:
        async with session as s:
            stored = await _run(s)
    else:
        stored = await _run(session)

    return {"title": title, "chunks": stored}


async def search(
    user_id: int,
    query: str,
    top_k: int = 5,
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """在指定用户的私有知识库中做向量检索。"""
    if not query or not query.strip():
        raise ValueError("查询文本不能为空")
    top_k = max(1, min(10, int(top_k)))

    query_vec = (await embedding_client.embed_texts([query.strip()]))[0]
    vec_literal = "[" + ",".join(str(x) for x in query_vec) + "]"

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> list[dict[str, Any]]:
        stmt = text(
            f"""
            SELECT title, source, content, chunk_index, 1 - (embedding <=> '{vec_literal}'::vector) AS similarity
            FROM user_knowledge
            WHERE user_id = :user_id AND embedding IS NOT NULL
            ORDER BY embedding <=> '{vec_literal}'::vector ASC
            LIMIT :top_k
            """
        )
        result = await s.execute(stmt, {"user_id": user_id, "top_k": top_k})
        return [
            {
                "title": row.title,
                "source": row.source,
                "content": row.content,
                "chunk_index": row.chunk_index,
                "similarity": round(float(row.similarity), 4),
            }
            for row in result
        ]

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)


async def list_documents(user_id: int, db: AsyncSession | None = None) -> list[dict[str, Any]]:
    """列出用户已上传的文档（按标题去重，附带块数）。"""
    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> list[dict[str, Any]]:
        stmt = text(
            """
            SELECT title, source, COUNT(*) AS chunks, MAX(created_at) AS latest
            FROM user_knowledge
            WHERE user_id = :user_id
            GROUP BY title, source
            ORDER BY latest DESC
            """
        )
        result = await s.execute(stmt, {"user_id": user_id})
        return [{"title": r.title, "source": r.source, "chunks": r.chunks} for r in result]

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)


async def delete_document(user_id: int, title: str, db: AsyncSession | None = None) -> int:
    """删除用户某篇文档的所有分块，返回删除条数。"""
    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> int:
        stmt = delete(UserKnowledge).where(
            UserKnowledge.user_id == user_id, UserKnowledge.title == title
        )
        result = await s.execute(stmt)
        await s.commit()
        return result.rowcount or 0

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)
