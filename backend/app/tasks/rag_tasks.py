"""RAG 知识库 Celery 任务（异步建索引）。"""

import asyncio
import logging

from app.celery_app import celery_app
from app.services.rag_service import build_index

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.rag_tasks.build_index_task")
def build_index_task() -> dict:
    """异步重建知识库向量索引。"""
    try:
        stats = _run(build_index(use_celery_engine=True))
        logger.info("知识库索引构建成功：%s", stats)
        return {"ok": True, **stats}
    except Exception as e:
        logger.exception("知识库索引构建失败")
        return {"ok": False, "error": str(e)}
