"""Celery 任务失败处理测试。

关键回归保护：此前所有任务都捕获异常返回 {"ok": False}，
Celery 会把失败当成 SUCCESS——重试与告警全部失效。
改造后异常必须向上抛，让 Celery 感知失败。
"""

import logging

import pytest

from app.celery_app import _alert_on_task_failure
from app.tasks.news_tasks import collect_weather_news
from app.tasks.rag_tasks import build_index_task
from app.tasks.weather_tasks import sync_weather_hourly


class TestRetryDeclaration:
    """重试参数声明（静态断言：所有依赖外部数据源的任务都应有自动重试）。"""

    @pytest.mark.parametrize(
        "task",
        [sync_weather_hourly, build_index_task, collect_weather_news],
        ids=["weather", "rag", "news"],
    )
    def test_声明了自动重试(self, task):
        assert task.autoretry_for == (Exception,)
        assert task.max_retries == 3
        assert task.retry_backoff is True
        assert task.retry_backoff_max == 60


class TestNoSwallow:
    # 下面三个测试必须是**同步**的：任务体内的 _run() 会 run_until_complete，
    # 而 async 测试运行在 pytest-asyncio 的事件循环里，嵌套起循环会报
    # 「Cannot run the event loop while another loop is running」。
    # 生产环境无此问题：Celery worker 线程里没有运行中的事件循环。
    def test_天气任务失败不再被吞掉(self, monkeypatch):
        async def boom(*args, **kwargs):
            raise RuntimeError("外部API挂了")

        monkeypatch.setattr("app.tasks.weather_tasks.fetch_and_store", boom)
        with pytest.raises(RuntimeError, match="外部API挂了"):
            sync_weather_hourly()

    def test_资讯任务失败不再被吞掉(self, monkeypatch):
        """collect_all 在任务内层函数里被调用，这里直接让 _job 的依赖炸掉。"""

        async def boom(*args, **kwargs):
            raise RuntimeError("数据源超时")

        # collect_all 在 _job 内是「from 源模块 import」，运行时才取值，
        # 因此要 patch 源模块上的属性（patch 任务模块上的名字会静默无效）
        monkeypatch.setattr("app.services.weather_news_service.collect_all", boom)
        with pytest.raises(RuntimeError, match="数据源超时"):
            collect_weather_news()

    def test_RAG任务失败不再被吞掉(self, monkeypatch):
        async def boom(*args, **kwargs):
            raise RuntimeError("embedding 挂了")

        monkeypatch.setattr("app.tasks.rag_tasks.build_index", boom)
        with pytest.raises(RuntimeError, match="embedding 挂了"):
            build_index_task()


class TestFailureAlert:
    def test_收到失败时记录结构化告警(self, caplog):
        with caplog.at_level(logging.ERROR, logger="celery.alert"):
            _alert_on_task_failure(
                sender=sync_weather_hourly,
                task_id="task-abc",
                exception=RuntimeError("最终失败"),
                retries=3,
            )

        records = [r for r in caplog.records if "Celery 任务最终失败" in r.getMessage()]
        assert records, "应输出告警日志"
        rec = records[0]
        assert rec.task == "app.tasks.weather_tasks.sync_weather_hourly"
        assert rec.task_id == "task-abc"
        assert rec.retries == 3
        assert rec.exc_info is not None  # 堆栈随日志落盘

    def test_无异常信息时不崩溃(self, caplog):
        with caplog.at_level(logging.ERROR, logger="celery.alert"):
            _alert_on_task_failure(sender=build_index_task, task_id="x", exception=None, retries=0)
        assert any("Celery 任务最终失败" in r.getMessage() for r in caplog.records)
