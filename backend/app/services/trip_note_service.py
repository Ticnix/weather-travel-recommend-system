"""行程笔记服务：CRUD + 导入解析。

导入来源：
- 上传文件：`.md` / `.txt`（整篇作为一篇笔记）、`.json`（单条或数组，支持批量）
- 粘贴文本：标题缺省时从 Markdown 一级标题或首个非空行推断
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trip_note import TripNote

logger = logging.getLogger(__name__)

# 单篇正文上限（字符）：防止异常大文件把库撑爆
MAX_CONTENT = 200_000


def derive_title(content: str, fallback: str = "未命名笔记") -> str:
    """从正文推断标题：优先 Markdown 标题行，其次首个非空行。"""
    for raw in (content or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            return (line.lstrip("#").strip() or fallback)[:255]
        return line[:255]
    return fallback


def _parse_json(text: str) -> list[dict[str, Any]]:
    """解析 JSON 导入内容，支持单条对象或数组（兼容本系统导出格式）。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败：{exc}") from exc

    items = data if isinstance(data, list) else [data]
    result: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        content = str(it.get("content") or "")
        title = str(it.get("title") or "").strip() or derive_title(content)
        note_date = it.get("note_date")
        location = it.get("location")
        result.append(
            {
                "title": title[:255],
                "content": content[:MAX_CONTENT],
                "note_date": str(note_date)[:10] if note_date else None,
                "location": str(location)[:128] if location else None,
            }
        )
    if not result:
        raise ValueError("JSON 中未找到有效笔记（每条需包含 content 字段）")
    return result


def parse_import_file(filename: str, raw: bytes) -> list[dict[str, Any]]:
    """解析上传文件，返回 [{title, content, note_date, location}, ...]。"""
    name = (filename or "").lower()
    text = raw.decode("utf-8", errors="ignore")

    if name.endswith(".json"):
        return _parse_json(text)

    # .md / .txt / 其他：整篇作为一篇笔记
    content = text[:MAX_CONTENT]
    if not content.strip():
        raise ValueError("文件内容为空，无法导入")
    base = filename.rsplit(".", 1)[0] if "." in (filename or "") else ""
    return [{"title": derive_title(content, base or "未命名笔记"), "content": content}]


async def create_note(
    user_id: int,
    title: str,
    content: str,
    note_date: str | None,
    location: str | None,
    db: AsyncSession,
) -> TripNote:
    note = TripNote(
        user_id=user_id,
        title=title[:255],
        content=(content or "")[:MAX_CONTENT],
        note_date=note_date,
        location=location,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def bulk_create(user_id: int, items: list[dict[str, Any]], db: AsyncSession) -> int:
    """批量导入，返回成功写入条数。"""
    created = 0
    for it in items:
        content = (it.get("content") or "")[:MAX_CONTENT]
        db.add(
            TripNote(
                user_id=user_id,
                title=(it.get("title") or derive_title(content))[:255],
                content=content,
                note_date=it.get("note_date"),
                location=it.get("location"),
            )
        )
        created += 1
    await db.commit()
    return created


async def list_notes(
    user_id: int,
    keyword: str | None,
    db: AsyncSession,
) -> list[TripNote]:
    stmt = select(TripNote).where(TripNote.user_id == user_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(TripNote.title.ilike(like) | TripNote.content.ilike(like))
    rows = await db.scalars(stmt.order_by(TripNote.updated_at.desc()))
    return list(rows)


async def get_note(user_id: int, note_id: int, db: AsyncSession) -> TripNote | None:
    note = await db.get(TripNote, note_id)
    if note is None or note.user_id != user_id:
        return None
    return note


async def update_note(
    user_id: int,
    note_id: int,
    fields: dict[str, Any],
    db: AsyncSession,
) -> TripNote | None:
    note = await get_note(user_id, note_id, db)
    if note is None:
        return None
    for key, value in fields.items():
        if key == "content" and value is not None:
            value = value[:MAX_CONTENT]
        setattr(note, key, value)
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(user_id: int, note_id: int, db: AsyncSession) -> int:
    result = await db.execute(
        delete(TripNote).where(TripNote.user_id == user_id, TripNote.id == note_id)
    )
    await db.commit()
    return result.rowcount or 0
