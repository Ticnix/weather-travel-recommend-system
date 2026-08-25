"""出行规划 Skill：融合「路线 + 天气」做多维度评分，输出多套带天气提示方案。

评分维度（三维，各归一化到 0~1 后加权求和，分值越高越推荐）：
1. 时间维度：耗时越短分越高
2. 费用维度：费用越低分越高
3. 天气维度：天气适宜度（降水越少、温度越舒适、风力越小，分越高）

评分公式：
    score = 0.4 * 时间分 + 0.3 * 费用分 + 0.3 * 天气分
（权重可配置，后续可让用户自定义偏好）
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import amap_client
from app.services.weather_service import fetch_weather

logger = logging.getLogger(__name__)

# 评分权重（时间/费用/天气）
WEIGHT_TIME = 0.4
WEIGHT_COST = 0.3
WEIGHT_WEATHER = 0.3


def _time_score(duration_min: float, max_duration: float) -> float:
    """时间分：耗时越短越高（0~1）。"""
    if max_duration <= 0:
        return 1.0
    return max(0.0, 1.0 - duration_min / max_duration)


def _cost_score(cost: float, max_cost: float) -> float:
    """费用分：费用越低越高（0~1）。"""
    if max_cost <= 0:
        return 1.0
    return max(0.0, 1.0 - cost / max_cost)


def _weather_score(weather_desc: str, temp_min: float | None, temp_max: float | None, precip: float | None) -> float:
    """天气适宜度评分（0~1）。

    - 降水越少分越高（降水>10mm 视为不利）
    - 温度越接近舒适区间 18~26°C 分越高
    - 天气描述含"雨/雪/雷/雹"扣分
    """
    score = 1.0

    # 降水惩罚
    if precip is not None:
        score -= min(0.5, precip / 20.0)  # 每 20mm 降 0.5

    # 温度惩罚（偏离舒适区）
    if temp_max is not None and temp_min is not None:
        avg = (temp_max + temp_min) / 2
        if avg < 10 or avg > 30:
            score -= 0.3
        elif avg < 18 or avg > 26:
            score -= 0.15

    # 恶劣天气关键词惩罚
    for bad in ("雨", "雪", "雷", "雹", "雾", "霾", "沙尘"):
        if bad in (weather_desc or ""):
            score -= 0.2
            break

    return max(0.0, min(1.0, score))


async def plan_travel(
    origin: str,
    destination: str,
    city: str | None = None,
) -> str:
    """出行规划主入口：路线规划 + 天气融合评分，返回结构化文本。"""
    if not origin or not destination:
        return "请提供出发地和目的地，例如「从广州南站到广州塔怎么走」。"

    # 1. 路线规划
    plan = await amap_client.plan_route(origin, destination, city)
    routes = plan.get("routes", [])
    if not routes:
        return plan.get("error", "路线规划失败，请稍后重试或提供更具体的地点。")

    # 2. 查天气（用于评分 + 提示）
    weather_desc = ""
    temp_min = temp_max = precip = None
    try:
        bundle = await fetch_weather(city or "广州")
        if bundle.daily:
            today = bundle.daily[0]
            weather_desc = today.weather_desc or ""
            temp_min, temp_max = today.temp_min, today.temp_max
            precip = today.precipitation_sum
    except Exception as exc:  # noqa: BLE001
        logger.warning("天气查询失败，评分降级为仅时间/费用: %s", exc)

    # 3. 多维度评分
    durations = [r["duration_min"] for r in routes]
    costs = [r["cost"] for r in routes]
    max_dur = max(durations) if durations else 1
    max_cost = max(costs) if costs else 1

    scored = []
    for r in routes:
        ts = _time_score(r["duration_min"], max_dur)
        cs = _cost_score(r["cost"], max_cost)
        ws = _weather_score(weather_desc, temp_min, temp_max, precip)
        total = WEIGHT_TIME * ts + WEIGHT_COST * cs + WEIGHT_WEATHER * ws
        r = {**r, "time_score": round(ts, 2), "cost_score": round(cs, 2), "weather_score": round(ws, 2), "total_score": round(total, 3)}
        scored.append(r)

    # 按总分降序
    scored.sort(key=lambda r: r["total_score"], reverse=True)

    # 4. 拼装输出文本
    lines = [
        f"从「{plan['origin']}」到「{plan['destination']}」的出行方案（共 {len(scored)} 套，按综合评分排序）：",
    ]
    if weather_desc:
        lines.append(f"当前天气参考：{weather_desc}"
                     + (f"，{temp_min}~{temp_max}°C" if temp_min is not None else "")
                     + (f"，降水 {precip}mm" if precip else ""))

    for i, r in enumerate(scored, 1):
        lines.append(
            f"{i}. 【{r['mode']}】耗时 {r['duration_min']} 分钟 / 距离 {r['distance_km']}km / 费用约 {r['cost']} 元"
            f"（综合评分 {r['total_score']}，时间 {r['time_score']} / 费用 {r['cost_score']} / 天气 {r['weather_score']}）"
        )
        if r.get("detail"):
            lines.append(f"   {r['detail']}")

    # 天气提示
    if weather_desc:
        if precip and precip > 0:
            lines.append(f"\n⚠️ 天气提示：当天有降水（{precip}mm），建议优先选择耗时短、换乘少的方案，备好雨具。")
        if any(bad in weather_desc for bad in ("雨", "雷", "雪")):
            lines.append("   雨天路滑，驾车请减速，步行/骑行注意安全。")

    return "\n".join(lines)