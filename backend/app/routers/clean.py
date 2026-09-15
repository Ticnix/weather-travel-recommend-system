"""清洗模块接口：CSV 上传、任务列表、详情/日志、下载清洗结果。"""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.clean import CleanTaskDetail, CleanTaskOut
from app.services.clean_service import (
    create_task_record,
    ensure_dirs,
    get_task,
    list_tasks,
)
from app.tasks.clean_tasks import run_clean

router = APIRouter(prefix="/api/v1/clean", tags=["数据清洗"])

ALLOWED_EXT = {".csv"}
MAX_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("/upload", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_csv(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> dict:
    """上传 CSV 并触发异步清洗任务（鉴权）。

    返回 task_id，前端可轮询 /clean/{task_id} 查看进度与日志。
    """
    ensure_dirs()
    filename = file.filename or "upload.csv"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="仅支持 .csv 文件")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="文件过大（>20MB）")

    task_id = str(uuid.uuid4())
    stored_path = Path(settings.UPLOAD_DIR) / f"{task_id}_{filename}"
    with open(stored_path, "wb") as f:
        f.write(content)

    # 创建 DB 任务记录
    await create_task_record(task_id, filename, str(stored_path), triggered_by=current.username)
    # 提交 Celery 异步任务
    run_clean.delay(task_id, filename, str(stored_path), triggered_by=current.username)

    return success(
        {"task_id": task_id, "filename": filename, "status": "pending"},
        message="已上传并提交清洗任务",
    )


@router.get("", response_model=dict)
async def list_clean_tasks(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
) -> dict:
    """清洗任务列表（鉴权）。"""
    tasks = await list_tasks(limit)
    return success(
        {"items": [CleanTaskOut.model_validate(t).model_dump() for t in tasks], "total": len(tasks)}
    )


@router.get("/{task_id}", response_model=dict)
async def get_clean_task(
    task_id: str, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    """清洗任务详情（含日志，鉴权）。"""
    task = await get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return success(CleanTaskDetail.model_validate(task).model_dump())


@router.get("/{task_id}/download", response_model=dict)
async def download_cleaned(
    task_id: str, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
):
    """下载清洗后的 CSV（鉴权）。"""
    task = await get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "success":
        raise HTTPException(status_code=400, detail=f"任务未完成（当前 {task.status}）")
    cleaned_path = Path(settings.CLEANED_DIR) / f"cleaned_{task_id}_{task.filename}"
    if not cleaned_path.exists():
        raise HTTPException(status_code=404, detail="清洗结果文件不存在")
    return FileResponse(path=str(cleaned_path), filename=cleaned_path.name, media_type="text/csv")
