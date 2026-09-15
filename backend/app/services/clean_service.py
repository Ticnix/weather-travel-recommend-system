"""清洗任务服务：DB 记录管理 + 触发 Celery 异步清洗。"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.clean_task import CleanTask


def _make_session() -> async_sessionmaker[AsyncSession]:
    """Celery 任务用的独立 NullPool 引擎。"""
    engine = create_async_engine(settings.DB_URL, poolclass=NullPool, pool_pre_ping=True)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


def ensure_dirs() -> None:
    """确保上传/清洗目录存在。"""
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CLEANED_DIR).mkdir(parents=True, exist_ok=True)


async def create_task_record(
    task_id: str,
    filename: str,
    stored_path: str,
    triggered_by: str | None = None,
    use_celery_engine: bool = False,
) -> CleanTask:
    """创建清洗任务记录（status=pending）。"""
    factory = _make_session() if use_celery_engine else AsyncSessionLocal
    async with factory() as db:
        task = CleanTask(
            task_id=task_id,
            filename=filename,
            stored_path=stored_path,
            status="pending",
            triggered_by=triggered_by,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task


async def update_task_stats(task_id: str, stats: dict, use_celery_engine: bool = False) -> None:
    """更新任务统计与状态。"""
    factory = _make_session() if use_celery_engine else AsyncSessionLocal
    async with factory() as db:
        task = await db.scalar(select(CleanTask).where(CleanTask.task_id == task_id))
        if task is None:
            return
        for k, v in stats.items():
            if hasattr(task, k):
                setattr(task, k, v)
        await db.commit()


async def mark_task_failed(task_id: str, error: str, use_celery_engine: bool = False) -> None:
    factory = _make_session() if use_celery_engine else AsyncSessionLocal
    async with factory() as db:
        task = await db.scalar(select(CleanTask).where(CleanTask.task_id == task_id))
        if task is None:
            return
        task.status = "failed"
        task.error = error
        await db.commit()


async def get_task(task_id: str) -> CleanTask | None:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(CleanTask).where(CleanTask.task_id == task_id))


async def list_tasks(limit: int = 20) -> list[CleanTask]:
    async with AsyncSessionLocal() as db:
        stmt = select(CleanTask).order_by(CleanTask.id.desc()).limit(limit)
        result = await db.scalars(stmt)
        return list(result)
