"""首页仪表盘聚合服务。

把「实时天气 + 今日提醒 + 穿搭建议 + 近期行程（含天气提醒）」聚合成一次请求返回，
供首页直接展示——用户不必为了看建议或行程而来回跳转页面。

设计：
- 天气提供方仍是 weather_service（和风 / Open-Meteo 自动降级）
- 穿搭建议复用 outfit_recommend Skill 的规则引擎（只取精简结果，避免首页过重）
- 行程来自 itinerary_service；**按行程地点解析城市后并发查天气**，
  跨城市行程（如「上海迪士尼」）也能拿到当地预报
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from app.services import index_service, itinerary_service
from app.services.city_dict import lookup_city
from app.services.weather_service import fetch_weather
from skills.outfit_recommend.scripts import outfit_engine

logger = logging.getLogger(__name__)

DEFAULT_CITY = "广州"
LOOKAHEAD_DAYS = 7  # 行程向后看几天
MAX_ITINERARY = 5  # 首页最多展示几条行程


def _resolve_city(location: str | None) -> str | None:
    """从行程地点解析城市规范名（如「上海迪士尼」→「上海」）。"""
    if not location:
        return None
    info = lookup_city(location)
    return info.name if info else None


def _build_tips(
    desc: str | None,
    temp_max: float | None,
    feels_like: float | None,
    precip: float | None,
    alerts: list[Any],
) -> list[dict[str, Any]]:
    """根据当日天气生成提醒条目（首页「今日提醒」）。"""
    tips: list[dict[str, Any]] = []
    text = desc or ""

    if precip and precip > 0:
        level = "danger" if precip >= 25 else "warning" if precip >= 10 else "info"
        tips.append(
            {
                "icon": "☔",
                "level": level,
                "title": f"有降水 {precip}mm",
                "text": "出门带伞，优先选耗时短、换乘少的路线",
            }
        )
    if any(k in text for k in ("雷", "雹")):
        tips.append(
            {
                "icon": "⛈️",
                "level": "danger",
                "title": "有强对流天气",
                "text": "尽量避免长时间户外活动，驾车注意减速",
            }
        )
    if temp_max is not None and temp_max >= 33:
        tips.append(
            {
                "icon": "🥵",
                "level": "warning",
                "title": f"高温 {temp_max:g}°C",
                "text": "注意防晒补水，避开正午时段户外活动",
            }
        )
    elif temp_max is not None and temp_max <= 12:
        tips.append(
            {
                "icon": "🥶",
                "level": "warning",
                "title": f"降温至 {temp_max:g}°C",
                "text": "注意保暖，建议加穿厚外套",
            }
        )
    if feels_like is not None and temp_max is not None and feels_like - temp_max >= 3:
        tips.append(
            {
                "icon": "💧",
                "level": "info",
                "title": f"体感 {feels_like:g}°C",
                "text": "湿度大、体感闷热，建议穿透气衣物",
            }
        )
    if any(k in text for k in ("风",)):
        tips.append(
            {
                "icon": "🌬️",
                "level": "info",
                "title": "风力较大",
                "text": "注意防风，户外避开高空坠物区域",
            }
        )
    for a in alerts or []:
        tips.append(
            {
                "icon": "⚠️",
                "level": "danger",
                "title": getattr(a, "title", "天气预警"),
                "text": getattr(a, "detail", "") or "请关注当地最新预警信息",
            }
        )

    if not tips:
        tips.append(
            {
                "icon": "🌤️",
                "level": "info",
                "title": "天气平稳",
                "text": "适合出行，按常规安排即可",
            }
        )
    return tips


async def _safe_weather(city: str) -> Any | None:
    try:
        return await fetch_weather(city)
    except Exception as exc:  # noqa: BLE001
        logger.warning("首页查询 %s 天气失败: %s", city, exc)
        return None


def _itinerary_hint(day_desc: str | None, day_precip: float | None, temp_max: float | None) -> str:
    """为单条行程生成一句天气提示。"""
    parts: list[str] = []
    if day_desc:
        parts.append(day_desc)
    if temp_max is not None:
        parts.append(f"{temp_max:g}°C")
    if day_precip:
        parts.append(f"降水 {day_precip}mm")
    if not parts:
        return "暂无该日预报"

    hint = "，".join(parts)
    if day_precip and day_precip >= 10:
        hint += "；建议带雨具或考虑改期"
    elif any(k in (day_desc or "") for k in ("雷", "雹")):
        hint += "；强对流天气，户外活动需谨慎"
    elif temp_max is not None and temp_max >= 33:
        hint += "；高温注意防晒补水"
    return hint


async def build_dashboard(
    user_id: int | None,
    city: str | None = None,
) -> dict[str, Any]:
    """构建首页数据。未登录时只返回天气与通用建议（无行程部分）。"""
    target_city = city or DEFAULT_CITY
    today = date.today()
    end = today + timedelta(days=LOOKAHEAD_DAYS)

    # 1) 天气 + 穿搭建议 + 生活指数并行获取
    weather_task = _safe_weather(target_city)
    outfit_task = outfit_engine.outfit_structured(target_city)
    index_task = index_service.summary_for_home(user_id, target_city)
    bundle, outfit, index_brief = await asyncio.gather(
        weather_task, outfit_task, index_task, return_exceptions=True
    )

    if isinstance(bundle, BaseException):
        bundle = None
    if isinstance(outfit, BaseException):
        outfit = None
    if isinstance(index_brief, BaseException):
        index_brief = []

    weather: dict[str, Any] = {}
    tips: list[dict[str, Any]] = []
    if bundle is not None:
        cur = bundle.current
        day0 = bundle.daily[0] if bundle.daily else None
        weather = {
            "city": target_city,
            "desc": cur.weather_desc,
            "temperature": cur.temperature,
            "feels_like": cur.feels_like,
            "humidity": cur.humidity,
            "temp_min": day0.temp_min if day0 else None,
            "temp_max": day0.temp_max if day0 else None,
            "precip": day0.precipitation_sum if day0 else None,
        }
        tips = _build_tips(
            cur.weather_desc,
            day0.temp_max if day0 else None,
            cur.feels_like,
            day0.precipitation_sum if day0 else None,
            list(bundle.alerts or []),
        )

    outfit_brief = None
    if outfit:
        outfit_brief = {
            "suggestion": outfit.get("suggestion", ""),
            "rules": (outfit.get("rules") or [])[:3],
            "temp_rule": outfit.get("temp_rule"),
        }

    # 2) 近期行程 + 逐条天气提示（未登录跳过）
    upcoming: list[dict[str, Any]] = []
    if user_id is not None:
        try:
            items = await itinerary_service.get_itinerary_by_date(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("首页查询行程失败: %s", exc)
            items = []

        today_str = today.isoformat()
        end_str = end.isoformat()
        items = [it for it in items if today_str <= it["date"] <= end_str][:MAX_ITINERARY]

        if items:
            # 按城市去重后并发查询，避免同一城市重复请求
            cities: dict[str, Any] = {}
            for it in items:
                c = _resolve_city(it.get("location")) or DEFAULT_CITY
                cities.setdefault(c, None)
            results = await asyncio.gather(
                *(_safe_weather(c) for c in cities), return_exceptions=True
            )
            # strict=True：gather 必然按输入顺序返回等长结果，
            # 一旦不等说明并发逻辑出了问题，应当立刻暴露而不是静默错位
            for c, res in zip(cities.keys(), results, strict=True):
                cities[c] = None if isinstance(res, BaseException) else res

            for it in items:
                c = _resolve_city(it.get("location")) or DEFAULT_CITY
                b = cities.get(c)
                day = None
                if b is not None:
                    for d in b.daily:
                        if d.date == it["date"]:
                            day = d
                            break
                upcoming.append(
                    {
                        **it,
                        "city": c,
                        "weather_hint": _itinerary_hint(
                            day.weather_desc if day else None,
                            day.precipitation_sum if day else None,
                            day.temp_max if day else None,
                        ),
                    }
                )

    return {
        "city": target_city,
        "date": today.isoformat(),
        "weather": weather,
        "tips": tips,
        "outfit": outfit_brief,
        # 生活指数：已按该用户的体质偏好与近期行程排序
        "indices": index_brief or [],
        "itinerary": {"upcoming": upcoming, "total": len(upcoming)},
        "logged_in": user_id is not None,
    }
