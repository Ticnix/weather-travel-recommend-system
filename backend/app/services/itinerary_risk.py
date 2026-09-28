"""行程 × 天气的冲突扫描（Day 51）。

与「出发前 30 分钟提醒」互补，不是替代：
- `reminder_tasks`：**当天**出发前 30 分钟提醒"该走了"；
- 本模块：提前若干天扫描**预报**与已排行程，发现冲突就给**改期建议**。

「气象出行推荐」真正该做的是后者——不是催你去，而是提前告诉你别去。

**阈值不另立一套**：风速 / 降水沿用 `settings.WIND_ALERT_KMH` / `RAIN_ALERT_MM`
（与 `weather_client._derive_alerts` 同一份配置），高温 / 降温阈值也放进 settings。
两处标准不一致会出现"预警页说没事、行程页说有事"，比不做还糟。

**为什么按中文描述匹配、而不是 WMO 码**：数据源可切换（Open-Meteo 用 WMO 码、
和风用 300 系列），同一场雨在两套编码里数字完全不同；`weather_desc` 关键词是
唯一在两个源上都成立的做法。

**为什么"雷阵雨"必须按描述判定**：雷阵雨常常是一阵就过，
`precipitation_sum`（日累计）可能只有 0.9mm，按降水阈值根本扫不出来，
但"爬山中遇到雷电"是真实且严重的安全风险。这也是 Day 29 测试抓出的同类缺陷。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 描述里出现这些词 → 直接判为危险级（即使日累计降水很小）
_SEVERE_WORDS = ("暴雨", "大暴雨", "特大暴雨", "雷阵雨", "雷暴", "强阵雨", "冰雹")
# 只要带"雨/雪"就说明有降水（两家数据源的描述都能命中）
_RAIN_WORDS = ("雨", "雪", "冰雹", "冻雨")
# 大风关键词（描述里带就提示，另外再看风速数值）
_WIND_WORDS = ("大风", "台风", "飓风")

# 明显是室内的活动：高温与降温对它不构成风险（室内有空调），
# 但降水/大风照样影响"怎么去"，所以只降级、不豁免。
_INDOOR_WORDS = (
    "室内",
    "博物馆",
    "展览",
    "美术馆",
    "商场",
    "影院",
    "电影",
    "餐厅",
    "美食",
    "下午茶",
    "书店",
    "咖啡",
    "温泉",
    "剧院",
)

_KIND_LABEL = {
    "rain": "降水",
    "wind": "大风",
    "heat": "高温",
    "drop": "降温",
}


@dataclass
class RiskHit:
    """一条命中的冲突。"""

    date: str
    kind: str  # rain / wind / heat / drop
    level: str  # warn / danger
    reason: str  # 给人看的一句原因
    indoor_only: bool = False  # True=只对户外活动成立


def is_indoor(*texts: str | None) -> bool:
    """从活动/标题/地点里判断是不是室内安排（判断不出来就按户外处理，保守）。"""
    joined = " ".join(t for t in texts if t)
    return any(word in joined for word in _INDOOR_WORDS)


def assess_day(
    day: Any,
    prev_day: Any | None = None,
    *,
    indoor: bool = False,
) -> RiskHit | None:
    """判断某一天的预报是否与行程冲突；没有冲突返回 None。

    `prev_day` 用于降温判断（与前一日最高温比较），拿不到就跳过这条规则——
    **不猜**，缺数据时不产生结论。
    """
    desc = (getattr(day, "weather_desc", None) or "").strip()
    precip = getattr(day, "precipitation_sum", None)
    wind = getattr(day, "wind_speed_max", None)
    tmax = getattr(day, "temp_max", None)
    tmin = getattr(day, "temp_min", None)

    temp_text = f"{tmin:g}~{tmax:g}℃" if tmin is not None and tmax is not None else "气温未知"

    # ① 强对流：按描述判定（日累计降水可能很小，见模块头说明）
    if any(word in desc for word in _SEVERE_WORDS):
        return RiskHit(
            date=day.date,
            kind="rain",
            level="danger",
            reason=f"{desc}（{temp_text}）",
        )

    # ② 降水阈值
    if precip is not None and precip >= settings.RAIN_ALERT_MM:
        level = "danger" if precip >= 25 else "warn"
        return RiskHit(
            date=day.date,
            kind="rain",
            level=level,
            reason=f"{desc or '降水'}，24h 降水约 {precip:g}mm（{temp_text}）",
        )

    # ③ 有降水但没到阈值：只在描述里明确带雨时轻提示
    if precip is None and any(word in desc for word in _RAIN_WORDS):
        return RiskHit(
            date=day.date,
            kind="rain",
            level="warn",
            reason=f"{desc}（{temp_text}）",
        )

    # ④ 大风
    if (wind is not None and wind >= settings.WIND_ALERT_KMH) or any(
        word in desc for word in _WIND_WORDS
    ):
        wind_text = f"最大风速 {wind:g}km/h" if wind is not None else desc or "大风"
        return RiskHit(
            date=day.date,
            kind="wind",
            level="warn",
            reason=f"{desc or '大风'}，{wind_text}",
        )

    # ⑤ 高温：只对户外活动成立
    if tmax is not None and tmax >= settings.HEAT_ALERT_C and not indoor:
        return RiskHit(
            date=day.date,
            kind="heat",
            level="warn",
            reason=f"{desc or '高温'}，最高 {tmax:g}℃",
            indoor_only=True,
        )

    # ⑥ 降温：与前一日最高温比较（拿不到前一天就不判，不猜）
    prev_max = getattr(prev_day, "temp_max", None) if prev_day is not None else None
    if tmax is not None and prev_max is not None and (prev_max - tmax) >= settings.TEMP_DROP_ALERT_C:
        return RiskHit(
            date=day.date,
            kind="drop",
            level="warn",
            reason=f"较前一天降温 {prev_max - tmax:.0f}℃（{temp_text}）",
        )

    return None


def score_day(day: Any) -> float | None:
    """给一天打分（**越低越适合出行**）；不适合或数据不全时返回 None。

    只做候选筛选，不追求精确：有明显降水/强对流的日子直接排除，
    其余按"降水少 + 温度接近舒适带（18~28℃）"排序。
    """
    desc = (getattr(day, "weather_desc", None) or "").strip()
    if any(word in desc for word in _SEVERE_WORDS):
        return None
    precip = getattr(day, "precipitation_sum", None) or 0
    if precip >= settings.RAIN_ALERT_MM:
        return None
    tmax = getattr(day, "temp_max", None)
    tmin = getattr(day, "temp_min", None)
    if tmax is None or tmin is None:
        return None
    score = precip * 2.0
    score += max(0.0, 18.0 - tmin) * 1.5  # 偏冷
    score += max(0.0, tmax - 28.0) * 1.5  # 偏热
    return score


def pick_alternative(forecast: dict[str, Any], after: str, exclude: str) -> Any | None:
    """在预报窗口里挑一个"更适合出行"的日期；没有合格的返回 None。

    `after` 只允许晚于今天（不能建议用户"改到昨天"），`exclude` 是要避开的那一天。
    """
    candidates: list[tuple[float, Any]] = []
    for date_str, day in forecast.items():
        if date_str == exclude or date_str <= after:
            continue
        score = score_day(day)
        if score is not None:
            candidates.append((score, day))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def build_advice(item: dict[str, Any], hit: RiskHit, alt: Any | None) -> tuple[str, str]:
    """生成提醒标题与正文（规则模板，零成本、可预期）。"""
    where = item.get("location") or item.get("title") or "行程"
    when = item.get("start_time") or "全天"
    label = _KIND_LABEL.get(hit.kind, "天气")

    title = f"⚠️ {item.get('date', '')[5:]} {where} 遇{label}"
    body = (
        f"你 {item.get('date', '')} {when} 安排了「{item.get('title', '')}」（{where}）："
        f"{hit.reason}。"
    )
    if alt is not None:
        alt_text = f"{alt.weather_desc or '天气'}"
        if alt.temp_min is not None and alt.temp_max is not None:
            alt_text += f" {alt.temp_min:g}~{alt.temp_max:g}℃"
        body += f"建议改到 {alt.date[5:]}（{alt_text}），那天更适合这类安排。"
    else:
        body += "预报窗口内没有明显更好的日子，建议调整成室内安排或顺延。"
    return title, body


def scan_items(
    items: list[dict[str, Any]],
    forecast: dict[str, Any],
    *,
    days_ahead: int = settings.RISK_SCAN_DAYS,
    today: str | None = None,
) -> list[dict[str, Any]]:
    """纯函数：把「行程列表 + 预报」变成冲突列表（便于脱离网络与数据库单测）。

    **预报缺失时既不报风险、也不当作晴天**：查不到某天的预报就跳过它，
    并在结果里不带该日期——这是检查清单明确要求的行为，
    因为"没数据"和"天气好"必须区分开，否则要么误报要么漏报。
    """
    if today is None:
        today = _today()
    hits: list[dict[str, Any]] = []
    for item in items:
        date_str = item.get("date")
        if not date_str or date_str < today:
            continue
        # 只扫最近 N 天：再远既没有可信预报，提醒也太早
        horizon_ok = date_str <= _plus_days(today, days_ahead)
        if not horizon_ok:
            continue
        day = forecast.get(date_str)
        if day is None:
            continue  # 预报缺失 → 不产生结论（不误报）
        prev_day = forecast.get(_plus_days(date_str, -1))
        indoor = is_indoor(item.get("activity"), item.get("title"), item.get("location"))
        hit = assess_day(day, prev_day, indoor=indoor)
        if hit is None:
            continue
        title, body = build_advice(item, hit, pick_alternative(forecast, today, date_str))
        hits.append(
            {
                "itinerary_id": item.get("id"),
                "date": date_str,
                "kind": hit.kind,
                "level": hit.level,
                "reason": hit.reason,
                "title": title,
                "body": body,
            }
        )
    return hits


def _today() -> str:
    """用户所在时区的"今天"。

    必须固定用 Asia/Shanghai：Celery 容器跑在 UTC，"今天"会与用户差 8 小时，
    傍晚之后的行程会被算到第二天去（Day 39 的行程提醒踩过同一个坑）。
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _plus_days(date_str: str, delta: int) -> str:
    """日期字符串加减天数（只用于日期比较，避免引入时区问题）。"""
    from datetime import date, timedelta

    try:
        base = date.fromisoformat(date_str)
    except ValueError:
        return date_str
    return (base + timedelta(days=delta)).isoformat()


async def assess_user_risks(user_id: int, db: Any, *, days_ahead: int | None = None) -> list[dict]:
    """扫描某用户未来若干天的行程，返回冲突列表。

    取不到预报时**返回空列表**（而不是报错或乱报）：宁可这一次没提醒，
    也不能在数据缺失时给出"看起来像结论"的东西。
    """
    from app.services import itinerary_service, weather_service

    today = _today()
    items = await itinerary_service.get_itinerary_by_date(user_id, None, db=db)
    if not items:
        return []

    try:
        bundle = await weather_service.fetch_weather(None)
    except Exception as exc:  # noqa: BLE001 天气拿不到不该让任务失败
        logger.warning("行程冲突扫描：取天气失败，本次跳过 user=%s: %s", user_id, exc)
        return []

    forecast = {d.date: d for d in bundle.daily}
    return scan_items(
        items,
        forecast,
        days_ahead=days_ahead if days_ahead is not None else settings.RISK_SCAN_DAYS,
        today=today,
    )
