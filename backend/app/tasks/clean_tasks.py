"""CSV 数据清洗 Celery 任务。"""

import asyncio
import logging
from pathlib import Path

from app.celery_app import celery_app
from app.core.config import settings
from app.services.clean_engine import clean_csv
from app.services.clean_service import (
    mark_task_failed,
    update_task_stats,
)

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task(name="app.tasks.clean_tasks.run_clean")
def run_clean(
    task_id: str, filename: str, stored_path: str, triggered_by: str | None = None
) -> dict:
    """异步执行 CSV 清洗。

    流程：
    1. 在 DB 创建任务记录（pending → running）
    2. 调用 Pandas 清洗引擎
    3. 更新任务统计与日志（success/failed）
    """
    cleaned_path = Path(settings.CLEANED_DIR) / f"cleaned_{task_id}_{filename}"

    # 标记 running
    _run(
        update_task_stats(
            task_id, {"status": "running", "log": "任务开始执行"}, use_celery_engine=True
        )
    )

    try:
        stats = clean_csv(stored_path, cleaned_path)
        _run(
            update_task_stats(
                task_id,
                {
                    "status": "success",
                    "total_rows": stats.total_rows,
                    "cleaned_rows": stats.cleaned_rows,
                    "duplicated_removed": stats.duplicated_removed,
                    "filled_missing": stats.filled_missing,
                    "filtered_outliers": stats.filtered_outliers,
                    "unit_standardized": stats.unit_standardized,
                    "log": stats.log_text,
                },
                use_celery_engine=True,
            )
        )
        logger.info("清洗任务 %s 成功：%s", task_id, stats.cleaned_rows)
        return {
            "ok": True,
            "task_id": task_id,
            "cleaned_rows": stats.cleaned_rows,
            "cleaned_path": str(cleaned_path),
        }
    except Exception as e:
        logger.exception("清洗任务 %s 失败", task_id)
        _run(mark_task_failed(task_id, str(e), use_celery_engine=True))
        return {"ok": False, "task_id": task_id, "error": str(e)}
