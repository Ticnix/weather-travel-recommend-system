"""行程笔记接口：CRUD + 导入 + 导出（均需鉴权，仅本人可见）。

导入方式：
- `POST /import`：上传文件（.md / .txt 作为单篇；.json 支持批量）
- `POST /import-text`：粘贴文本
导出方式：
- `GET /export/all`：全部笔记导出为 JSON（可再次导入，用于备份/迁移）
- `GET /{id}/export`：单篇导出为 .md 文件
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.trip_note import (
    TripNoteCreate,
    TripNoteImportText,
    TripNoteOut,
    TripNoteUpdate,
)
from app.services import trip_note_service

router = APIRouter(prefix="/api/v1/notes", tags=["行程笔记"])

# 上传上限：笔记是纯文本，2MB 足够
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@router.get("", response_model=dict)
async def list_notes(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    keyword: str | None = None,
) -> dict:
    """查询本人的行程笔记（按更新时间倒序；keyword 同时匹配标题与正文）。"""
    rows = await trip_note_service.list_notes(current.id, keyword, db)
    items = [TripNoteOut.model_validate(r).model_dump() for r in rows]
    return success({"items": items, "total": len(items)})


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: TripNoteCreate,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """新建笔记。"""
    note = await trip_note_service.create_note(
        current.id, payload.title, payload.content, payload.note_date, payload.location, db
    )
    return success(TripNoteOut.model_validate(note).model_dump(), message="笔记已创建")


@router.post("/import-text", response_model=dict, status_code=status.HTTP_201_CREATED)
async def import_text(
    payload: TripNoteImportText,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """粘贴文本导入为一篇笔记（标题缺省时自动从正文推断）。"""
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    title = (payload.title or "").strip() or trip_note_service.derive_title(payload.content)
    note = await trip_note_service.create_note(
        current.id, title, payload.content, payload.note_date, payload.location, db
    )
    return success(TripNoteOut.model_validate(note).model_dump(), message="已导入 1 篇笔记")


@router.post("/import", response_model=dict, status_code=status.HTTP_201_CREATED)
async def import_file(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(description=".md / .txt / .json")],
) -> dict:
    """上传文件导入笔记。

    - `.md` / `.txt`：整篇作为一篇笔记
    - `.json`：支持单条或数组批量导入（兼容「导出全部」的格式）
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件过大（上限 2MB）")

    try:
        items = trip_note_service.parse_import_file(file.filename or "", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    created = await trip_note_service.bulk_create(current.id, items, db)
    return success(
        {"created": created, "titles": [i["title"] for i in items][:10]},
        message=f"导入成功，新增 {created} 篇笔记",
    )


@router.get("/export/all", response_model=dict)
async def export_all(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """导出全部笔记（JSON，可再次通过导入功能恢复）。"""
    rows = await trip_note_service.list_notes(current.id, None, db)
    return success(
        [
            {
                "title": r.title,
                "content": r.content,
                "note_date": r.note_date,
                "location": r.location,
            }
            for r in rows
        ]
    )


@router.get("/{note_id}", response_model=dict)
async def get_note(
    note_id: int,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """笔记详情。"""
    note = await trip_note_service.get_note(current.id, note_id, db)
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return success(TripNoteOut.model_validate(note).model_dump())


@router.put("/{note_id}", response_model=dict)
async def update_note(
    note_id: int,
    payload: TripNoteUpdate,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """更新笔记（只更新传入的字段）。"""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    note = await trip_note_service.update_note(current.id, note_id, fields, db)
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return success(TripNoteOut.model_validate(note).model_dump(), message="已保存")


@router.delete("/{note_id}", response_model=dict)
async def delete_note(
    note_id: int,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """删除笔记。"""
    deleted = await trip_note_service.delete_note(current.id, note_id, db)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return success({"deleted": deleted}, message="已删除")


@router.get("/{note_id}/export")
async def export_note_md(
    note_id: int,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """导出单篇笔记为 .md 文件（浏览器直接下载）。"""
    note = await trip_note_service.get_note(current.id, note_id, db)
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    filename = quote(f"{note.title}.md")
    return Response(
        content=note.content or "",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
