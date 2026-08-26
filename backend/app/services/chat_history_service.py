"""对话历史服务：多轮对话上下文的持久化与读取。

- add_message：保存一轮对话（用户提问 / AI 回答）
- get_recent_history：读取某会话最近 N 轮，用于构造多轮上下文
- 均按 user_id 隔离，多租户安全
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.chat_message import ChatMessage

# 拼进多轮上下文的历史条数（取最近 N 条消息，超出截断）
HISTORY_LIMIT = 10


async def add_message(
    user_id: int | None,
    conversation_id: str,
    role: str,
    content: str,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """保存一条消息。匿名用户（user_id=None）不持久化，仅返回。"""
    if user_id is None:
        return {"role": role, "content": content, "saved": False}

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> dict[str, Any]:
        msg = ChatMessage(
            user_id=user_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        s.add(msg)
        await s.commit()
        await s.refresh(msg)
        return {"id": msg.id, "role": msg.role, "content": msg.content, "saved": True}

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)


async def get_recent_history(
    user_id: int | None,
    conversation_id: str,
    limit: int = HISTORY_LIMIT,
    db: AsyncSession | None = None,
) -> list[dict[str, str]]:
    """读取最近 N 条消息（按时间正序返回），用于多轮上下文。"""
    if user_id is None:
        return []

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> list[dict[str, str]]:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.conversation_id == conversation_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
        rows = (await s.execute(stmt)).scalars().all()
        # 反转为时间正序
        rows = list(reversed(rows))
        return [{"role": r.role, "content": r.content} for r in rows]

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)
