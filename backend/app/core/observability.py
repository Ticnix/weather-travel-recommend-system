"""可观测性基础设施：请求 ID 贯穿、结构化日志、轻量指标。

三个部件，解决三个问题：

1. **request_id 贯穿**
   每个请求生成唯一 ID（或继承上游的 X-Request-ID），通过 contextvars
   在整个调用链传播——包括所有 service 层日志。排查问题时「用一个 ID
   就能串起一次请求的全部日志」，不用再靠时间戳猜。

2. **结构化日志**
   日志输出为 JSON 单行（字段固定：ts/level/logger/msg/request_id +
   调用方通过 extra 传入的业务字段），便于日志采集与检索。
   相比自由文本，「字段化」意味着可以按 request_id、path、status 直接过滤。

3. **轻量指标（/metrics）**
   进程内计数器：按路由统计请求数 / 错误数 / 总耗时。
   不引入 Prometheus 等依赖——当前「看调用量与错误率」的需求，
   几十行代码即可满足，等真有可视化需求时再升级采集方式，对外接口不变。

设计约束：
- **/health 的逻辑不放在本模块**：健康检查是部署回滚的依据，必须尽可能简单可靠
- 中间件注册与日志配置走 `setup_observability(app)`，一次调用全部完成
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# 请求 ID：contextvars 天然适配 asyncio——每个请求一份独立的"上下文副本"，
# 并发请求之间互不串号。
# ---------------------------------------------------------------------------
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """获取当前请求的 request_id（非请求上下文中返回 '-'）。"""
    return request_id_var.get()


class RequestIdFilter(logging.Filter):
    """把 request_id 注入每条日志记录，供 Formatter 取用。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """JSON 单行日志。

    extra 字段走白名单：业务代码通过 `logger.info("...", extra={"path": ...})`
    传业务字段，这里只输出白名单内的键——否则 logging 内部自带的
    几十个属性（funcName/lineno/msecs...）会把每行日志撑爆。
    """

    _EXTRA_KEYS = (
        "method",
        "path",
        "route",
        "status",
        "duration_ms",
        "task_id",
        "task",
        "retries",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key in self._EXTRA_KEYS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """全局日志配置为 JSON 格式（幂等：重复调用不会叠加 handler）。

    关闭 uvicorn.access：请求日志由我们的中间件输出（带 request_id/耗时/路由），
    两份 access log 内容重复只会干扰检索。
    """
    # Windows 下 stdout/stderr 重定向到文件时默认用本地编码（GBK），
    # JSON 里的中文会变成一堆问号；Linux 容器本来就是 UTF-8，reconfigure 无副作用
    import contextlib
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):  # 个别环境不允许重配流，跳过即可
                stream.reconfigure(encoding="utf-8")

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)

    logging.getLogger("uvicorn.access").disabled = True


# ---------------------------------------------------------------------------
# 轻量指标：进程内计数器
# ---------------------------------------------------------------------------


class Metrics:
    """按路由聚合的请求指标（进程内，重启归零——够用即可，不做持久化）。"""

    def __init__(self) -> None:
        self.started_at: float = time.time()
        self._routes: dict[str, dict[str, float]] = defaultdict(
            lambda: {"count": 0, "errors": 0, "total_ms": 0.0}
        )

    def observe(self, route: str, status: int, duration_ms: float) -> None:
        bucket = self._routes[route]
        bucket["count"] += 1
        if status >= 500:
            bucket["errors"] += 1
        bucket["total_ms"] += duration_ms

    def snapshot(self) -> dict[str, Any]:
        routes = {
            path: {
                **stats,
                "avg_ms": round(stats["total_ms"] / stats["count"], 1) if stats["count"] else 0,
                "error_rate": round(stats["errors"] / stats["count"], 4) if stats["count"] else 0,
            }
            for path, stats in sorted(self._routes.items())
        }
        total = sum(s["count"] for s in routes.values())
        errors = sum(s["errors"] for s in routes.values())
        return {
            "uptime_s": round(time.time() - self.started_at, 1),
            "total": total,
            "errors": errors,
            "error_rate": round(errors / total, 4) if total else 0,
            "routes": routes,
        }


metrics = Metrics()

# ---------------------------------------------------------------------------
# 请求中间件
# ---------------------------------------------------------------------------


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求：注入 request_id → 计时 → 结构化日志 → 更新指标。"""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 继承上游的 X-Request-ID（若网关/前端已生成），否则生成
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 走到这里的是全局异常处理器没接住的异常，记录后继续抛给框架
            logging.getLogger("app.request").exception(
                "请求处理未捕获异常",
                extra={"method": request.method, "path": request.url.path},
            )
            request_id_var.reset(token)
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        # 用路由模板而不是真实 path 聚合指标——
        # 否则 /news/84、/news/85 会被聚成两条，指标失去意义
        route = getattr(request.scope.get("route"), "path", request.url.path)
        status = response.status_code

        metrics.observe(route, status, duration_ms)
        logging.getLogger("app.request").info(
            "请求完成",
            extra={
                "method": request.method,
                "path": request.url.path,
                "route": route,
                "status": status,
                "duration_ms": duration_ms,
            },
        )

        response.headers["X-Request-ID"] = rid
        request_id_var.reset(token)
        return response


def setup_observability(app: FastAPI) -> None:
    """日志配置 + 中间件挂载（main.py 里一次调用完成）。"""
    setup_logging()
    # add_middleware 的添加顺序与执行顺序相反；本项目只有这一个中间件
    app.add_middleware(RequestContextMiddleware)
