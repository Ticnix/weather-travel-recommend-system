"""对话历史服务：多轮对话上下文的持久化与读取。

- add_message：保存一轮对话（用户提问 / AI 回答）
- get_recent_history：读取某会话最近 N 轮，用于构造多轮上下文
- list_conversations：会话列表（供前端「历史对话」侧栏）
- get_conversation_messages：读取整个会话的消息（供前端回放）
- delete_conversation：删除整个会话
- 均按 user_id 隔离，多租户安全
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.chat_message import ChatMessage

# 拼进多轮上下文的历史条数（取最近 N 条消息，超出截断）
HISTORY_LIMIT = 10

# 会话列表扫描的原始消息上限（用于在内存中分组，避免复杂 SQL 聚合）
CONVERSATION_SCAN_LIMIT = 500


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


async def list_conversations(
    user_id: int,
    limit: int = 30,
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """列出用户的会话（按最后活跃时间倒序），供前端「历史对话」侧栏使用。

    实现：取该用户最近 CONVERSATION_SCAN_LIMIT 条消息在内存中分组，
    避免复杂的 SQL 聚合；标题取会话中**最早一条用户提问**的前 40 字。
    """
    if user_id is None:
        return []

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.id.desc())
            .limit(CONVERSATION_SCAN_LIMIT)
        )
        rows = (await s.execute(stmt)).scalars().all()

        groups: dict[str, dict[str, Any]] = {}
        for r in rows:  # 按 id 倒序遍历：首次遇到即该会话最新一条
            g = groups.setdefault(
                r.conversation_id,
                {
                    "conversation_id": r.conversation_id,
                    "count": 0,
                    "title": "",
                    "last_at": r.created_at,
                },
            )
            g["count"] += 1
            if r.role == "user":
                # 倒序遍历中最后赋值的是最早的用户提问 → 用它当标题
                g["title"] = r.content[:40].replace("\n", " ")

        items = sorted(groups.values(), key=lambda x: x["last_at"], reverse=True)
        for it in items:
            it["last_at"] = it["last_at"].isoformat() if it["last_at"] else None
        return items[:limit]

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)


async def get_conversation_messages(
    user_id: int,
    conversation_id: str,
    limit: int = 200,
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """读取整个会话的消息（时间正序），供前端回放历史对话。"""
    if user_id is None:
        return []

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.conversation_id == conversation_id,
            )
            .order_by(ChatMessage.id.asc())
            .limit(limit)
        )
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)


async def delete_conversation(
    user_id: int,
    conversation_id: str,
    db: AsyncSession | None = None,
) -> int:
    """删除整个会话，返回删除的消息条数。"""
    if user_id is None:
        return 0

    owns_db = db is None
    session = db or AsyncSessionLocal()

    async def _run(s: AsyncSession) -> int:
        result = await s.execute(
            delete(ChatMessage).where(
                ChatMessage.user_id == user_id,
                ChatMessage.conversation_id == conversation_id,
            )
        )
        await s.commit()
        return result.rowcount or 0

    if owns_db:
        async with session as s:
            return await _run(s)
    return await _run(session)
