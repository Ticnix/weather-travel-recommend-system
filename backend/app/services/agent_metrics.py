"""Agent 运行指标（Day 41）。

**为什么需要它**：多智能体架构"看起来更优雅"不是理由。
要判断值不值，必须能回答三个问题：

1. 延迟高了多少？（多 Agent 意味着多次 LLM 调用）
2. token 花了多少？（每个领域 Agent 都要带自己的系统提示与工具描述）
3. 复合问题是不是真的路由对了？（领域命中分布）

没有数据，架构讨论就只是审美偏好。

进程内聚合、重启归零——与 `core/observability.Metrics` 同样的取舍：
当前的需求是"跑一批对比看趋势"，几十行足够，等要做可视化再换实现。
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class AgentMetrics:
    """按运行模式（single / multi）聚合的 Agent 指标。"""

    def __init__(self) -> None:
        self.started_at: float = time.time()
        self._buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "runs": 0,
                "llm_calls": 0,
                "tool_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_ms": 0.0,
                "errors": 0,
                "domain_hits": defaultdict(int),
                "domain_counts": defaultdict(int),  # 命中 N 个领域的请求数
            }
        )

    def observe(
        self,
        mode: str,
        *,
        duration_ms: float,
        llm_calls: int = 0,
        tool_calls: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        domains: list[str] | None = None,
        error: bool = False,
    ) -> None:
        """记录一次 Agent 运行。"""
        bucket = self._buckets[mode]
        bucket["runs"] += 1
        bucket["llm_calls"] += llm_calls
        bucket["tool_calls"] += tool_calls
        bucket["prompt_tokens"] += prompt_tokens
        bucket["completion_tokens"] += completion_tokens
        bucket["total_ms"] += duration_ms
        bucket["errors"] += 1 if error else 0

        hits = list(domains or [])
        for key in hits:
            bucket["domain_hits"][key] += 1
        bucket["domain_counts"][len(hits)] += 1

    def snapshot(self) -> dict[str, Any]:
        """各模式的汇总（含均值，便于直接比较）。"""
        result: dict[str, Any] = {
            "uptime_s": round(time.time() - self.started_at, 1),
            "modes": {},
        }
        for mode, bucket in sorted(self._buckets.items()):
            runs = bucket["runs"] or 1  # 避免除零；runs=0 的模式不会出现在这里
            result["modes"][mode] = {
                "runs": bucket["runs"],
                "avg_ms": round(bucket["total_ms"] / runs, 1),
                "avg_llm_calls": round(bucket["llm_calls"] / runs, 2),
                "avg_tool_calls": round(bucket["tool_calls"] / runs, 2),
                "avg_prompt_tokens": round(bucket["prompt_tokens"] / runs, 1),
                "avg_completion_tokens": round(bucket["completion_tokens"] / runs, 1),
                "total_tokens": bucket["prompt_tokens"] + bucket["completion_tokens"],
                "errors": bucket["errors"],
                "domain_hits": dict(bucket["domain_hits"]),
                "domain_counts": {str(k): v for k, v in sorted(bucket["domain_counts"].items())},
            }
        return result

    def reset(self) -> None:
        """清空（跑对比前调用，避免历史数据混进均值）。"""
        self._buckets.clear()


agent_metrics = AgentMetrics()
