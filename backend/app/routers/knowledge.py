"""RAG 知识库管理接口：建索引、语义检索。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.knowledge import IndexResult, SearchHit, SearchRequest
from app.services import rag_service

router = APIRouter(prefix="/api/v1/knowledge", tags=["RAG 知识库"])


@router.post("/index", response_model=dict)
async def build_index(current: CurrentUser) -> dict:
    """全量重建向量索引（鉴权）：加载文档 -> 分块 -> embedding -> 入库。"""
    try:
        stats = await rag_service.build_index()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return success(IndexResult(**stats).model_dump(), message="索引构建完成")


@router.get("/index/async", response_model=dict)
async def build_index_async(current: CurrentUser) -> dict:
    """通过 Celery 异步重建索引（鉴权），立即返回任务 ID。"""
    from app.tasks.rag_tasks import build_index_task

    task = build_index_task.delay()
    return success({"task_id": task.id, "status": "PENDING"}, message="已提交异步建索引任务")


@router.post("/search", response_model=dict)
async def search(
    body: SearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """语义检索（公开）：输入问题，返回 Top5 相关知识片段。"""
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="查询文本不能为空")
    items = await rag_service.search(body.query, top_k=body.top_k)
    hits = [SearchHit(**it).model_dump() for it in items]
    return success({"items": hits, "total": len(hits)}, message="检索完成")


@router.get("/search", response_model=dict)
async def search_get(
    q: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    top_k: int = 5,
) -> dict:
    """语义检索（公开，GET 形式，便于快速验证）。"""
    if not q.strip():
        raise HTTPException(status_code=400, detail="查询文本不能为空")
    items = await rag_service.search(q, top_k=top_k)
    hits = [SearchHit(**it).model_dump() for it in items]
    return success({"items": hits, "total": len(hits)}, message="检索完成")
