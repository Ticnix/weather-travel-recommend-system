"""出行规划 Skill 核心逻辑（scripts）。

独立于 FastAPI 上下文，可单独测试。依赖公共服务：
- app.services.amap_client（路线规划）
- app.services.weather_service（天气）

评分规则见 references/scoring-rules.md。
"""

from __future__ import annotations

from typing import Any

from app.services import amap_client
from app.services.weather_service import fetch_weather

WEIGHT_TIME = 0.4
WEIGHT_COST = 0.3
WEIGHT_WEATHER = 0.3


def time_score(duration_min: float, max_duration: float) -> float:
    if max_duration <= 0:
        return 1.0
    return max(0.0, 1.0 - duration_min / max_duration)


def cost_score(cost: float, max_cost: float) -> float:
    if max_cost <= 0:
        return 1.0
    return max(0.0, 1.0 - cost / max_cost)


def weather_score(
    weather_desc: str, temp_min: float | None, temp_max: float | None, precip: float | None
) -> float:
    score = 1.0
    if precip is not None:
        score -= min(0.5, precip / 20.0)
    if temp_max is not None and temp_min is not None:
        avg = (temp_max + temp_min) / 2
        if avg < 10 or avg > 30:
            score -= 0.3
        elif avg < 18 or avg > 26:
            score -= 0.15
    for bad in ("雨", "雪", "雷", "雹", "雾", "霾", "沙尘"):
        if bad in (weather_desc or ""):
            score -= 0.2
            break
    return max(0.0, min(1.0, score))


async def run(origin: str, destination: str, city: str | None = None) -> str:
    """出行规划主入口，返回结构化文本。"""
    data = await plan_structured(origin, destination, city)
    if data.get("error"):
        return data["error"]
    if data.get("hint"):
        return data["hint"]

    plan = data
    scored = plan["routes"]
    weather_desc = plan.get("weather", {}).get("desc", "")
    temp_min = plan["weather"].get("temp_min")
    temp_max = plan["weather"].get("temp_max")
    precip = plan["weather"].get("precip")

    lines = [
        f"从「{plan['origin']}」到「{plan['destination']}」的出行方案（共 {len(scored)} 套，按综合评分排序）："
    ]
    if weather_desc:
        lines.append(
            f"当前天气参考：{weather_desc}"
            + (f"，{temp_min}~{temp_max}°C" if temp_min is not None else "")
            + (f"，降水 {precip}mm" if precip else "")
        )

    for i, r in enumerate(scored, 1):
        lines.append(
            f"{i}. 【{r['mode']}】耗时 {r['duration_min']} 分钟 / 距离 {r['distance_km']}km / 费用约 {r['cost']} 元"
            f"（综合评分 {r['total_score']}，时间 {r['time_score']} / 费用 {r['cost_score']} / 天气 {r['weather_score']}）"
        )
        if r.get("detail"):
            lines.append(f"   {r['detail']}")

    if weather_desc:
        if precip and precip > 0:
            lines.append(
                f"\n⚠️ 天气提示：当天有降水（{precip}mm），建议优先选择耗时短、换乘少的方案，备好雨具。"
            )
        if any(bad in weather_desc for bad in ("雨", "雷", "雪")):
            lines.append("   雨天路滑，驾车请减速，步行/骑行注意安全。")

    return "\n".join(lines)


async def plan_structured(
    origin: str,
    destination: str,
    city: str | None = None,
    origin_point: dict[str, Any] | None = None,
    destination_point: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """出行规划结构化入口，返回可直接用于前端渲染的 dict。

    结构：
    {
      "origin": "…", "destination": "…",
      "weather": {"desc": "…", "temp_min":…, "temp_max":…, "precip":…},
      "routes": [ {"mode","duration_min","distance_km","cost","detail",
                    "time_score","cost_score","weather_score","total_score"}, … ],
      "error"?: str, "hint"?: str
    }
    """
    if not origin or not destination:
        return {"error": "请提供出发地和目的地，例如「从广州南站到广州塔怎么走」。"}

    plan = await amap_client.plan_route(origin, destination, city, origin_point, destination_point)
    routes = plan.get("routes", [])
    if not routes:
        err = plan.get("error", "路线规划失败，请稍后重试或提供更具体的地点。")
        return {"error": err, "origin": origin, "destination": destination, "routes": []}

    # 天气
    weather_desc = ""
    temp_min = temp_max = precip = None
    try:
        bundle = await fetch_weather(city or "广州")
        if bundle.daily:
            today = bundle.daily[0]
            weather_desc = today.weather_desc or ""
            temp_min, temp_max = today.temp_min, today.temp_max
            precip = today.precipitation_sum
    except Exception:  # noqa: BLE001
        pass

    # 评分
    durations = [r["duration_min"] for r in routes]
    costs = [r["cost"] for r in routes]
    max_dur = max(durations) if durations else 1
    max_cost = max(costs) if costs else 1

    scored = []
    for r in routes:
        ts = time_score(r["duration_min"], max_dur)
        cs = cost_score(r["cost"], max_cost)
        ws = weather_score(weather_desc, temp_min, temp_max, precip)
        total = WEIGHT_TIME * ts + WEIGHT_COST * cs + WEIGHT_WEATHER * ws
        scored.append(
            {
                **r,
                "time_score": round(ts, 2),
                "cost_score": round(cs, 2),
                "weather_score": round(ws, 2),
                "total_score": round(total, 3),
            }
        )

    scored.sort(key=lambda r: r["total_score"], reverse=True)

    return {
        "origin": plan.get("origin", origin),
        "destination": plan.get("destination", destination),
        "weather": {
            "desc": weather_desc,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "precip": precip,
        },
        "routes": scored,
    }
