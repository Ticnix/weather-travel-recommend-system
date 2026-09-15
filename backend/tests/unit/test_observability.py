"""可观测性测试：request_id 贯穿、结构化日志、指标聚合、健康检查降级。

/health 的「全部可用返回 200」路径由本地部署实测覆盖（依赖真实 Redis），
这里重点测两个单元可验证的部分：JSON 日志的正确性、依赖故障时的 503 降级。
"""

import json
import logging

import pytest

from app.core.observability import (
    JsonFormatter,
    Metrics,
    RequestIdFilter,
    get_request_id,
)


def _record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    """构造一条日志记录（等价于 logger.info(msg, extra=extra) 后的 record）。"""
    rec = logging.LogRecord("test.logger", logging.INFO, "test.py", 1, msg, None, None)
    for key, value in extra.items():
        setattr(rec, key, value)
    return rec


class TestJsonFormatter:
    def test_输出为合法JSON且含基础字段(self):
        rec = _record()
        data = json.loads(JsonFormatter().format(rec))
        assert data["msg"] == "hello"
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["request_id"] == "-"  # 非请求上下文中的默认值

    def test_extra白名单字段被输出(self):
        rec = _record("请求完成", method="GET", path="/x", status=200, duration_ms=1.5)
        data = json.loads(JsonFormatter().format(rec))
        assert data["method"] == "GET"
        assert data["path"] == "/x"
        assert data["status"] == 200
        assert data["duration_ms"] == 1.5

    def test_logging内部属性不外泄(self):
        rec = _record()
        data = json.loads(JsonFormatter().format(rec))
        # 若不加白名单，record 自带的几十个属性都会混进 JSON
        assert "funcName" not in data
        assert "threadName" not in data
        assert "processName" not in data

    def test异常堆栈被附加(self):
        import sys

        try:
            raise ValueError("boom")
        except ValueError:
            rec = logging.LogRecord("t", logging.ERROR, "f", 1, "挂了", None, sys.exc_info())
        data = json.loads(JsonFormatter().format(rec))
        assert "boom" in data["exc"]

    def test_RequestIdFilter注入request_id(self):
        rec = logging.LogRecord("t", logging.INFO, "f", 1, "m", None, None)
        assert RequestIdFilter().filter(rec) is True
        assert rec.request_id == "-"  # type: ignore[attr-defined]


class TestMetrics:
    def test_计数与平均耗时(self):
        metrics = Metrics()
        metrics.observe("/x", 200, 10.0)
        metrics.observe("/x", 200, 30.0)
        snapshot = metrics.snapshot()

        assert snapshot["total"] == 2
        assert snapshot["errors"] == 0
        assert snapshot["routes"]["/x"]["avg_ms"] == 20.0

    def test_5xx计为错误(self):
        metrics = Metrics()
        metrics.observe("/y", 500, 5.0)
        metrics.observe("/y", 200, 5.0)
        snapshot = metrics.snapshot()

        assert snapshot["errors"] == 1
        assert snapshot["routes"]["/y"]["error_rate"] == pytest.approx(0.5)

    def test_不同路由分开聚合(self):
        metrics = Metrics()
        metrics.observe("/a", 200, 1.0)
        metrics.observe("/b", 200, 2.0)
        snapshot = metrics.snapshot()

        assert set(snapshot["routes"]) == {"/a", "/b"}


class TestRequestIdContext:
    async def test_请求上下文外返回占位符(self, client):
        # 中间件在每个请求结束时 reset contextvar，测试进程里拿到的是默认值
        assert get_request_id() == "-"


class TestRequestMiddleware:
    """中间件行为（走真实 ASGI 链路）。"""

    async def test_响应头带request_id(self, client):
        resp = await client.get("/health")
        assert resp.headers["x-request-id"]

    async def test_继承上游request_id(self, client):
        resp = await client.get("/health", headers={"X-Request-ID": "my-trace-123"})
        assert resp.headers["x-request-id"] == "my-trace-123"


class TestHealthDegraded:
    async def test_数据库故障时返回503(self, client, monkeypatch):
        """DB 挂了必须 503 而不是 200——deploy.sh 靠状态码判断是否回滚。"""

        class BrokenSession:
            async def __aenter__(self):
                raise RuntimeError("db down")

            async def __aexit__(self, *args: object):
                return False

        monkeypatch.setattr("app.main.AsyncSessionLocal", BrokenSession)
        resp = await client.get("/health")

        assert resp.status_code == 503
        checks = resp.json()["data"]["checks"]
        assert checks["db"].startswith("fail")
        # Redis 在测试环境可用时应为 ok；不可用时也应是明确的 fail 而不是 200
        assert checks["redis"] == "ok" or checks["redis"].startswith("fail")
