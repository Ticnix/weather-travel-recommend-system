"""资讯 / 公告模块 CRUD。

读取列表/详情公开；创建/更新/删除需鉴权（管理员或发布者）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_delete_prefix, cached
from app.core.deps import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.models.news import News
from app.schemas.news import NewsCreate, NewsOut, NewsUpdate

router = APIRouter(prefix="/api/v1/news", tags=["资讯公告"])


@router.get("", response_model=dict)
async def list_news(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    keyword: str | None = None,
    published_only: bool = False,
) -> dict:
    # 缓存键需覆盖全部筛选参数，避免不同条件互相串数据
    cache_key = f"news:list:{page}:{page_size}:{category}:{keyword}:{published_only}"

    async def _load() -> dict:
        stmt = select(News)
        if category:
            stmt = stmt.where(News.category == category)
        if keyword:
            stmt = stmt.where(News.title.ilike(f"%{keyword}%"))
        if published_only:
            stmt = stmt.where(News.is_published.is_(True))
        total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await db.scalars(
            stmt.order_by(News.is_top.desc(), News.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return {
            "items": [NewsOut.model_validate(n).model_dump() for n in rows],
            "total": total or 0,
            "page": page,
            "page_size": page_size,
        }

    # 热点读接口缓存 5 分钟；新增/修改/删除时会主动清除该前缀
    data = await cached(cache_key, 300, _load)
    return success(data)


@router.get("/{news_id}", response_model=dict)
async def get_news(news_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    news = await db.get(News, news_id)
    if news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资讯不存在")
    # 阅读量 +1
    news.view_count = (news.view_count or 0) + 1
    await db.commit()
    return success(NewsOut.model_validate(news).model_dump())


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_news(
    payload: NewsCreate, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    news = News(**payload.model_dump())
    if not news.author:
        news.author = current.nickname or current.username
    db.add(news)
    await db.commit()
    await db.refresh(news)
    await cache_delete_prefix("news:list:")  # 列表缓存失效
    return success(NewsOut.model_validate(news).model_dump(), message="发布成功")


@router.put("/{news_id}", response_model=dict)
async def update_news(
    news_id: int, payload: NewsUpdate, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    news = await db.get(News, news_id)
    if news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资讯不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(news, field, value)
    await db.commit()
    await db.refresh(news)
    await cache_delete_prefix("news:list:")  # 列表缓存失效
    return success(NewsOut.model_validate(news).model_dump(), message="更新成功")


@router.delete("/{news_id}", response_model=dict)
async def delete_news(
    news_id: int, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    news = await db.get(News, news_id)
    if news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资讯不存在")
    await db.delete(news)
    await db.commit()
    await cache_delete_prefix("news:list:")  # 列表缓存失效
    return success(message="删除成功")
