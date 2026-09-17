"""气象时序分析服务（Day 42）。

在此之前，所有统计都是"在原始行上现算 GROUP BY"——
超表建了却没真正用起来。本模块把统计切到**连续聚合**上：

| | 现算 GROUP BY（旧） | 连续聚合（新） |
| --- | --- | --- |
| 每次查询扫描 | 时间范围内全部原始行（每小时一行，几年就是几万行） | 预聚合的日行（一年 365 行） |
| 计算时机 | 每次请求 | 后台策略每小时增量刷新 |
| 历史越久 | 越慢 | 基本不变 |

⚠️ **两个必须小心的细节**：

1. **日切时区**：聚合用的是 `time_bucket('1 day', time, 'Asia/Shanghai')`，
   产出的 `day` 是"当地午夜"的时间戳。如果直接取它的 UTC 日期，
   会整体错一天（当地 9/14 00:00 = UTC 9/13 16:00）。
   所以查询里统一转成本地日期再输出。

2. **同比要先确认有同期数据**：系统数据从 2026-08 才开始，
   查 2026-09 的去年同期时**库里没有 2025-09 的数据**。
   这时必须如实返回"无同期数据可比"，而不是拿 0 去算出一个假的 -100%。
   编造出来的同比比没有同比更糟——它看起来像真的。
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 与连续聚合的日切时区保持一致（改这里必须同步改 app/db/analytics.py）
LOCAL_TZ = "Asia/Shanghai"

# 日均值的含义：只要当天的日统计行都参与，日期由参数区间控制
DAILY_SERIES_SQL = """
SELECT (day AT TIME ZONE :tz)::date AS date,
       location_code,
       temp_avg, temp_max, temp_min,
       precip_sum, precip_avg, humidity_avg, samples
FROM weather_daily
WHERE location_code = :loc
  AND day >= (CAST(:since AS timestamp) AT TIME ZONE :tz)
  AND day <  (CAST(:until AS timestamp) AT TIME ZONE :tz)
ORDER BY day
"""

# 区间汇总：直接由日行再聚合（比扫原始行便宜得多）
PERIOD_SUMMARY_SQL = """
SELECT count(*)                            AS days,
       count(temp_avg)                     AS temp_days,
       avg(temp_avg)                       AS temp_avg,
       max(temp_max)                       AS temp_max,
       min(temp_min)                       AS temp_min,
       sum(precip_sum)                     AS precip_total,
       avg(humidity_avg)                   AS humidity_avg,
       sum(samples)                        AS samples
FROM weather_daily
WHERE location_code = :loc
  AND day >= (CAST(:since AS timestamp) AT TIME ZONE :tz)
  AND day <  (CAST(:until AS timestamp) AT TIME ZONE :tz)
"""


def month_period(year: int, month: int) -> tuple[date, date]:
    """某月的 [起, 止) 日期区间（止为下月 1 日，便于半开区间查询）。"""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """按月平移（delta 为 -1 表示上个月），用于环比。"""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def align_previous_end(prev_start: date, prev_end: date, days: int) -> date:
    """把同期区间截到「相同的天数」，让两边口径可比（纯函数）。

    **为什么必须做**：9 月 17 日查"今年 9 月 vs 去年 9 月"，
    本期只有 17 天、同期是完整 30 天，降水差必然是负数——
    那不是"今年雨少"，只是"天数少"。这类结论会被当成真实趋势，
    比算不出来更危险。

    对齐方式取与本期相同的**天号**（1~17 日 vs 1~17 日），
    这也是气象统计里「同期对比」的常规口径。
    """
    last_day = calendar.monthrange(prev_start.year, prev_start.month)[1]
    target = prev_start.replace(day=min(max(days, 1), last_day))
    return min(target + timedelta(days=1), prev_end)


def _round(value: Any, digits: int = 1) -> float | None:
    """转 float 并保留位数；None 原样返回（缺数据不能当成 0）。"""
    if value is None:
        return None
    return round(float(value), digits)


def delta(current: Any, previous: Any, digits: int = 1) -> float | None:
    """差值（缺失任一侧返回 None——不能把"没有数据"算成 0）。

    这条规则看着不起眼，但是整个模块最重要的一条：
    把缺失当成 0，同比就会算出"今年降水比去年少了 100%"这种假结论。
    """
    if current is None or previous is None:
        return None
    return round(float(current) - float(previous), digits)


def delta_text(value: float | None, unit: str, digits: int = 1) -> str:
    """把差值写成自然语言（纯函数，便于单测）。"""
    if value is None:
        return "无数据"
    if abs(value) < 10 ** (-digits):
        return "持平"
    sign = "+" if value > 0 else "-"
    return f"{sign}{abs(value):.{digits}f}{unit}"


def build_verdict(temp_delta: float | None, precip_delta: float | None, kind_label: str) -> str:
    """一句话结论，例如「同比：气温 +1.2°C，降水 -30.5mm」。"""
    parts: list[str] = []
    if temp_delta is not None:
        parts.append(f"气温 {delta_text(temp_delta, '°C')}")
    if precip_delta is not None:
        parts.append(f"降水 {delta_text(precip_delta, 'mm')}")
    if not parts:
        return f"{kind_label}：两侧均无可用数据"
    return f"{kind_label}：" + "，".join(parts)


def summarize_rows(rows: list[Any]) -> dict[str, Any]:
    """把日行聚成区间摘要（纯函数，输入是 SQL 行）。

    放在 Python 里而不是全靠 SQL，是为了让"区间概览"的算法能被单测覆盖，
    也让 PERIOD_SUMMARY_SQL 与它互为校验（两者结果应当一致）。
    """
    temps = [float(r.temp_avg) for r in rows if r.temp_avg is not None]
    highs = [float(r.temp_max) for r in rows if r.temp_max is not None]
    lows = [float(r.temp_min) for r in rows if r.temp_min is not None]
    precips = [float(r.precip_sum or 0) for r in rows]
    humidities = [float(r.humidity_avg) for r in rows if r.humidity_avg is not None]

    return {
        "days": len(rows),
        "samples": sum(int(r.samples or 0) for r in rows),
        "temp_avg": _round(sum(temps) / len(temps)) if temps else None,
        "temp_max": _round(max(highs)) if highs else None,
        "temp_min": _round(min(lows)) if lows else None,
        "precip_total": _round(sum(precips)) if rows else None,
        "humidity_avg": _round(sum(humidities) / len(humidities)) if humidities else None,
    }


# ---------------------------------------------------------------------------
# 数据库查询
# ---------------------------------------------------------------------------


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "date": row.date.isoformat() if isinstance(row.date, date) else str(row.date),
        "temp_avg": _round(row.temp_avg),
        "temp_max": _round(row.temp_max),
        "temp_min": _round(row.temp_min),
        "precip_sum": _round(row.precip_sum),
        "precip_avg": _round(row.precip_avg),
        "humidity_avg": _round(row.humidity_avg),
        "samples": int(row.samples or 0),
    }


async def daily_series(
    db: AsyncSession,
    location_code: str = "gz",
    days: int = 90,
    end: date | None = None,
) -> list[dict[str, Any]]:
    """日粒度序列（趋势图数据源）。end 缺省为今天。"""
    until = (end or date.today()) + timedelta(days=1)
    since = until - timedelta(days=days + 1)
    rows = await db.execute(
        text(DAILY_SERIES_SQL),
        {"loc": location_code, "tz": LOCAL_TZ, "since": since, "until": until},
    )
    return [_row_to_dict(row) for row in rows]


async def period_summary(
    db: AsyncSession, location_code: str, start: date, end: date
) -> dict[str, Any]:
    """区间汇总（end 为半开上界）。"""
    row = (
        await db.execute(
            text(PERIOD_SUMMARY_SQL),
            {"loc": location_code, "tz": LOCAL_TZ, "since": start, "until": end},
        )
    ).one()
    return {
        "days": int(row.days or 0),
        "samples": int(row.samples or 0),
        "temp_avg": _round(row.temp_avg),
        "temp_max": _round(row.temp_max),
        "temp_min": _round(row.temp_min),
        "precip_total": _round(row.precip_total),
        "humidity_avg": _round(row.humidity_avg),
    }


async def compare_month(
    db: AsyncSession,
    location_code: str = "gz",
    kind: str = "yoy",
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    """月度同比 / 环比。

    kind="yoy" → 对比去年同月；kind="mom" → 对比上个月。
    **任一侧无数据都返回 available=False 并说明原因**，绝不拿 0 充数。
    """
    today = date.today()
    cur_year = year or today.year
    cur_month = month or today.month

    if kind == "mom":
        prev_year, prev_month = shift_month(cur_year, cur_month, -1)
        kind_label = "环比"
    else:
        prev_year, prev_month = cur_year - 1, cur_month
        kind_label = "同比"

    cur_start, cur_end = month_period(cur_year, cur_month)
    prev_start, prev_end = month_period(prev_year, prev_month)

    # 本期若"进行中"（今天落在本月内），同期截到相同天数，否则两边不可比
    aligned = False
    elapsed = 0
    if cur_end > today >= cur_start:
        elapsed = (today - cur_start).days + 1
        prev_end = align_previous_end(prev_start, prev_end, elapsed)
        aligned = True

    current = await period_summary(db, location_code, cur_start, cur_end)
    previous = await period_summary(db, location_code, prev_start, prev_end)

    cur_label = f"{cur_year}-{cur_month:02d}"
    prev_label = f"{prev_year}-{prev_month:02d}"

    result: dict[str, Any] = {
        "kind": kind,
        "kind_label": kind_label,
        "location_code": location_code,
        "current_period": cur_label,
        "previous_period": prev_label,
        "current": current,
        "previous": previous,
        "diff": {
            "temp_avg": delta(current["temp_avg"], previous["temp_avg"]),
            "temp_max": delta(current["temp_max"], previous["temp_max"]),
            "precip_total": delta(current["precip_total"], previous["precip_total"], 1),
            "humidity_avg": delta(current["humidity_avg"], previous["humidity_avg"]),
        },
        # 口径是否已对齐（本期进行中时为 True，并截取同期相同天数）
        "aligned": aligned,
        "aligned_days": elapsed if aligned else None,
        "available": False,
        "reason": "",
    }

    if current["days"] == 0 and previous["days"] == 0:
        result["reason"] = f"{cur_label} 与 {prev_label} 都没有统计数据"
        return result
    if current["days"] == 0:
        result["reason"] = f"{cur_label} 没有统计数据"
        return result
    if previous["days"] == 0:
        result["reason"] = (
            f"{prev_label} 没有统计数据（同比需要去年同期的数据，可用历史归档回补后重试）"
        )
        return result

    result["available"] = True
    result["verdict"] = build_verdict(
        result["diff"]["temp_avg"], result["diff"]["precip_total"], kind_label
    )
    note = (
        f"本期 {current['days']} 天 / {current['samples']} 个样本，"
        f"同期 {previous['days']} 天 / {previous['samples']} 个样本"
    )
    if aligned:
        note += f"；本期进行中，同期已按相同天数（1~{elapsed} 日）对齐，口径可比"
    result["sample_note"] = note
    return result


async def refresh_daily_aggregate(since: date | None = None) -> bool:
    """手动刷新连续聚合（回补历史数据后立即生效用）。

    ⚠️ 必须在 **autocommit** 连接上执行：
    `refresh_continuous_aggregate` 不允许跑在事务块里
    （实测报 `cannot run inside a transaction block`）。
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(settings.DB_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                # 显式 ::timestamptz：传进来的是 date，函数要 timestamptz
                text(
                    "CALL refresh_continuous_aggregate('weather_daily', (:since)::timestamptz, NULL)"
                ),
                {"since": since},
            )
        logger.info("连续聚合已刷新 since=%s", since)
        return True
    except Exception as exc:  # noqa: BLE001 刷新失败不该让调用方失败
        logger.warning("连续聚合刷新失败: %s", exc)
        return False
    finally:
        await engine.dispose()
