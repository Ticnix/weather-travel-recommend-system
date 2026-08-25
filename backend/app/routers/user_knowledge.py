"""用户私有知识库接口：上传、检索、列表、删除（均需鉴权）。

用户可上传自己的出行计划、旅游攻略、旅行笔记等文本，
系统切块向量化后按 user_id 隔离存储，检索时只查自己的内容。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.user_knowledge import UserKnowledgeCreate, UserKnowledgeSearch
from app.services import user_knowledge_service

router = APIRouter(prefix="/api/v1/my-knowledge", tags=["用户私有知识库"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_document(
    payload: UserKnowledgeCreate,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """上传文档/计划，切块向量化入库。"""
    try:
        result = await user_knowledge_service.add_document(
            user_id=current.id,
            title=payload.title,
            content=payload.content,
            source=payload.source,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success(result, message="文档已入库")


@router.post("/search", response_model=dict)
async def search_my_knowledge(
    payload: UserKnowledgeSearch,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """在本人私有知识库中检索。"""
    try:
        items = await user_knowledge_service.search(
            user_id=current.id, query=payload.query, top_k=payload.top_k, db=db
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success({"items": items, "total": len(items)}, message="检索完成")


@router.get("", response_model=dict)
async def list_my_documents(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """列出本人已上传的文档。"""
    items = await user_knowledge_service.list_documents(current.id, db=db)
    return success({"items": items, "total": len(items)})


@router.delete("/{title}", response_model=dict)
async def delete_my_document(
    title: str,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """删除本人某篇文档（按标题）。"""
    deleted = await user_knowledge_service.delete_document(current.id, title, db=db)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="文档不存在")
    return success({"deleted": deleted}, message="删除成功")