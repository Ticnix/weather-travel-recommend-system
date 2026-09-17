"""AI 一键排行程 Skill（Day 40）。

输入「想去哪 / 几天 / 偏好」，输出**可直接保存到行程表**的结构化行程。

编排链：
  1. 解析需求   → 城市 / 天数 / 偏好        parse_request（纯函数）
  2. 查天气     → 每天是否适合户外          needs_indoor（纯函数）
  3. 找候选景点 → amap suggest_places       （有 Key 走高德，无 Key 回落内置地标）
  4. 交 LLM     → 结构化行程                llm_client.ainvoke_json
  5. 审计并纠正 → 雨天不排户外              audit_plan（纯函数）

**第 5 步是这里最关键的设计**：不能把「模型会听话」当作正确性依赖。
提示词里写"雨天不要排户外"只是建议，模型完全可能照排不误。
所以在生成之后逐条检查、把坏天气日里的户外项换成室内候选，于是：

- 「雨天不排户外」从"希望如此"变成"返回结果里不可能出现"
- 审计是纯函数，可以脱离 LLM 单测（LLM 输出不稳定，指望它做断言等于自找 flaky）

这也是本项目对「LLM 参与的功能怎么测」的答案：
**把可验证的约束抽成纯函数，LLM 只负责创意部分。**
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.services import amap_client
from app.services.city_dict import all_supported_cities, lookup_city
from app.services.llm_client import ainvoke_json
from app.services.weather_service import fetch_weather

logger = logging.getLogger(__name__)

DEFAULT_CITY = "广州"
DEFAULT_DAYS = 2
MAX_DAYS = 5

# 坏天气判定阈值：降水到这个量、或出现强对流、或高温，都不适合排户外
RAIN_MM = 5.0
HOT_C = 35.0

_CN_DIGITS = {
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

# 偏好关键词 → 规范标签（既用于提示词，也用于候选景点排序）
PREFERENCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "美食": ("吃", "美食", "小吃", "餐厅", "探店"),
    "亲子": ("亲子", "小孩", "孩子", "儿童"),
    "拍照": ("拍照", "摄影", "出片", "打卡"),
    "文化": ("文化", "历史", "博物馆", "古迹", "展"),
    "自然": ("自然", "爬山", "徒步", "公园", "山水", "露营"),
    "购物": ("购物", "逛街", "商场", "买买买"),
    "夜景": ("夜景", "夜游", "酒吧", "晚上"),
    "轻松": ("轻松", "休闲", "不累", "慢节奏"),
}


class PlanItem(BaseModel):
    """一条行程安排。"""

    time: str = Field(description="开始时间，24 小时制 HH:MM，如 09:30")
    title: str = Field(description="地点名称，如「白云山」")
    activity: str = Field(default="", description="活动，如「徒步登山」「午餐」")
    reason: str = Field(default="", description="为什么把它安排在这里（结合天气与偏好）")
    weather_adjusted: bool = Field(default=False, description="是否因天气原因被调整过")


class PlanDay(BaseModel):
    """一天的安排。"""

    date: str = Field(description="日期 YYYY-MM-DD")
    weather: str = Field(default="", description="当天天气概述")
    weather_note: str = Field(default="", description="天气相关提醒，如「有雨，已改室内」")
    items: list[PlanItem] = Field(default_factory=list)


class TripPlan(BaseModel):
    """LLM 产出的行程主体。"""

    city: str = Field(description="城市")
    days: int = Field(description="天数")
    summary: str = Field(default="", description="整体思路，一两句话")
    plan: list[PlanDay] = Field(default_factory=list, description="逐日安排")


class TripRequest(BaseModel):
    """解析后的用户需求。"""

    city: str
    days: int
    preferences: list[str] = Field(default_factory=list)
    city_assumed: bool = False  # 城市是回落默认值推断出来的，前端需提示用户确认


def _cn_to_int(text: str) -> int | None:
    """中文数字转整数，覆盖 一~十 与 十三 / 二十三 这类写法。"""
    if not text:
        return None
    if text == "十":
        return 10
    if text.startswith("十"):  # 十三
        return 10 + _CN_DIGITS.get(text[1:], 0)
    if "十" in text:  # 二十三
        head, _, tail = text.partition("十")
        return _CN_DIGITS.get(head, 0) * 10 + (_CN_DIGITS.get(tail, 0) if tail else 0)
    return _CN_DIGITS.get(text)


def parse_days(text: str) -> int:
    """从自然语言里解析天数（超过上限按上限截断）。

    要同时认「天」和「日」：「三日游」「两日游」是极常见的说法，
    只认「天」的话这些话会被当成没提天数，静默用默认值——
    用户拿到一个 2 天行程却说自己要 3 天，是最容易被忽略的一类错。
    """
    if "周末" in text:
        return 2

    matched = re.search(r"(\d+)\s*[天日]", text)
    if matched:
        return max(1, min(int(matched.group(1)), MAX_DAYS))

    matched = re.search(r"([一二两三四五六七八九十]+)\s*[天日]", text)
    if matched:
        value = _cn_to_int(matched.group(1))
        if value:
            return max(1, min(value, MAX_DAYS))

    return DEFAULT_DAYS


def parse_city(text: str) -> tuple[str, bool]:
    """解析城市，返回 (城市, 是否为推断值)。

    先按支持城市列表做包含匹配，比 lookup_city 的模糊规则更可控；
    查不到就回落默认城市**并标记为推断**——前端会提示用户确认。
    默默给出另一个城市的行程，比明确说「按广州规划的，对吗」更糟。
    """
    for name in all_supported_cities():
        if name in text:
            return name, False
    info = lookup_city(text)
    if info:
        return info.name, False
    return DEFAULT_CITY, True


def parse_preferences(text: str) -> list[str]:
    """解析偏好标签（可能命中多个）。"""
    return [
        label
        for label, keywords in PREFERENCE_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]


def parse_request(query: str) -> TripRequest:
    """把一句自然语言需求解析成结构化请求。"""
    text = (query or "").strip()
    city, assumed = parse_city(text)
    return TripRequest(
        city=city,
        days=parse_days(text),
        preferences=parse_preferences(text),
        city_assumed=assumed,
    )


def needs_indoor(desc: str | None, precip: float | None, temp_max: float | None) -> bool:
    """当天是否不适合排户外活动。

    判据（任一成立即需要室内）：
    - 强对流（雷/雹/暴雨/大雪/台风）：这类天气排户外不只是体验差，是安全风险
    - 降水量达到阈值
    - 高温
    """
    text = desc or ""
    if any(keyword in text for keyword in ("雷", "雹", "暴雨", "大雪", "台风")):
        return True
    if precip is not None and precip >= RAIN_MM:
        return True
    return temp_max is not None and temp_max >= HOT_C


INDOOR_KEYWORDS = (
    "博物馆",
    "展馆",
    "美术馆",
    "纪念馆",
    "科技馆",
    "图书馆",
    "商场",
    "购物中心",
    "剧院",
    "影院",
    "水族馆",
    "室内",
    "茶馆",
    "书店",
)

OUTDOOR_KEYWORDS = (
    "公园",
    "山",
    "湖",
    "岛",
    "江",
    "河",
    "广场",
    "街",
    "步行",
    "骑行",
    "徒步",
    "露营",
    "夜游",
    "植物园",
    "沙滩",
    "温泉",
    "塔",
    "桥",
    "园",
)


def is_outdoor(*texts: str) -> bool:
    """判断一个安排是否属于户外。

    规则：命中室内关键词 → 室内；否则命中户外关键词 → 户外；
    都不命中时**按户外处理**——保守一点，宁可多提醒一次，
    也别漏掉「雨天安排爬山」这种真正会出问题的组合。
    """
    joined = " ".join(text for text in texts if text)
    if any(keyword in joined for keyword in INDOOR_KEYWORDS):
        return False
    if any(keyword in joined for keyword in OUTDOOR_KEYWORDS):
        return True
    return True


async def collect_candidates(
    city: str, preferences: list[str], limit: int = 12
) -> dict[str, list[str]]:
    """收集候选景点，分成室内 / 户外两组。

    数据来源优先高德 inputtips；无 Key 时 amap_client 会回落内置地标库，
    再拿不到就用一组通用兜底——保证 LLM 至少有东西可排，不至于空手而归。
    """
    keywords = ["景点", *preferences]
    names: list[str] = []
    for keyword in keywords:
        try:
            places = await amap_client.suggest_places(keyword, city=city, limit=6)
        except Exception as exc:  # noqa: BLE001 检索失败不该让整个排程挂掉
            logger.warning("景点检索失败 keyword=%s: %s", keyword, exc)
            continue
        names.extend(place.get("name", "") for place in places if place.get("name"))

    unique = list(dict.fromkeys(name for name in names if name))
    if not unique:
        unique = [f"{city}博物馆", f"{city}人民公园"]

    indoor = [name for name in unique if not is_outdoor(name)]
    outdoor = [name for name in unique if is_outdoor(name)]
    return {"indoor": indoor[:limit], "outdoor": outdoor[:limit], "all": unique[:limit]}


def audit_plan(
    plan: TripPlan,
    weather_by_date: dict[str, dict[str, Any]],
    indoor_pool: list[str] | None = None,
) -> tuple[TripPlan, list[str]]:
    """审计行程与天气的冲突，并就地修正。返回 (行程, 调整说明)。

    对每一天：若当天不适合户外，遍历该天的户外项——
    1. 还有室内候选 → 直接替换，并标注 weather_adjusted
    2. 没有候选了   → 保留内容但标注，并把提醒写进 weather_note

    调整说明会一路返回给前端展示：**"改了什么、为什么改"要让用户看见**，
    静默替换用户刚看到的内容比不改更让人困惑。
    """
    pool = list(indoor_pool or [])
    fixes: list[str] = []

    for day in plan.plan:
        info = weather_by_date.get(day.date)
        if not info or not info.get("needs_indoor"):
            continue

        replaced = 0
        desc = info.get("desc") or "天气不佳"
        for item in day.items:
            if not is_outdoor(item.title, item.activity):
                continue
            if pool:
                replacement = pool.pop(0)
                fixes.append(f"{day.date}：{item.title}（户外）→ {replacement}（室内，当天{desc}）")
                item.title = replacement
                item.activity = "室内游览"
            else:
                fixes.append(f"{day.date}：{item.title} 建议改为室内活动（当天{desc}）")
            item.weather_adjusted = True
            replaced += 1

        if replaced:
            note = f"当天{desc}，已把 {replaced} 项户外安排调整为室内"
            day.weather_note = f"{day.weather_note}；{note}" if day.weather_note else note

    return plan, fixes


PLAN_SYSTEM_PROMPT = """你是本地行程规划师，负责把「日期 + 天气 + 候选景点」排成一份可直接执行的行程。

硬性要求：
1. 每天 3~4 项，每项必须给出时间（24 小时制 HH:MM）、地点、活动、以及一句话安排理由
2. 标注了「不适合户外」的日期，**只能安排室内场所**（博物馆/展馆/商场等）
3. 同一天的地点要顺路，不要在城市两端来回横跳
4. 只使用我给出的候选地点，**不要编造不存在的地方或餐厅**
5. 结合用户偏好选点：偏好自然就多排公园山地，偏好文化就多排展馆古迹
6. 饭点安排用餐（可写「XX 附近用餐」，不必编造店名）
"""


def _build_prompt(
    request: TripRequest,
    dates: list[str],
    weather_lines: list[str],
    candidates: dict[str, list[str]],
) -> str:
    """拼装排程提示词：把「约束」交给模型，把「校验」留给自己。"""
    preferences = "、".join(request.preferences) if request.preferences else "无特别偏好"
    weather_text = "\n".join(weather_lines) if weather_lines else "（天气数据不可用）"
    indoor = "、".join(candidates["indoor"]) if candidates["indoor"] else "（无）"
    outdoor = "、".join(candidates["outdoor"]) if candidates["outdoor"] else "（无）"

    return f"""请为以下需求排一份 {request.days} 天行程。

城市：{request.city}
日期：{"、".join(dates)}
用户偏好：{preferences}

逐日天气：
{weather_text}

候选景点（请从中挑选）：
- 室内候选：{indoor}
- 户外候选：{outdoor}

请严格按 日期(YYYY-MM-DD) → 每日若干项（time/title/activity/reason）的结构输出。"""


async def _collect_weather(
    city: str, dates: list[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """取逐日天气，返回 (按日期的天气字典, 供提示词的文本行)。

    天气失败**不阻断排程**：没有天气约束也能出行程，
    只是少了「雨天规避」这一层——比整个功能报错好得多。
    """
    weather_by_date: dict[str, dict[str, Any]] = {}
    lines: list[str] = []

    try:
        bundle = await fetch_weather(city)
    except Exception as exc:  # noqa: BLE001
        logger.warning("排程取天气失败 %s: %s", city, exc)
        return weather_by_date, lines

    by_date = {day.date: day for day in bundle.daily}
    for date_str in dates:
        day = by_date.get(date_str)
        if day is None:
            continue
        info = {
            "desc": day.weather_desc,
            "precip": day.precipitation_sum,
            "temp_max": day.temp_max,
            "temp_min": day.temp_min,
            "needs_indoor": needs_indoor(day.weather_desc, day.precipitation_sum, day.temp_max),
        }
        weather_by_date[date_str] = info
        flag = "（不适合户外，请安排室内）" if info["needs_indoor"] else ""
        lines.append(
            f"{date_str}：{info['desc']}，{info['temp_min']}~{info['temp_max']}°C，"
            f"降水 {info['precip']}mm{flag}"
        )
    return weather_by_date, lines


async def generate(query: str, today: date | None = None) -> dict[str, Any]:
    """完整排程链路：解析 → 天气 → 候选 → LLM → 审计。"""
    request = parse_request(query)
    start = today or date.today()
    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(request.days)]

    weather_by_date, weather_lines = await _collect_weather(request.city, dates)
    candidates = await collect_candidates(request.city, request.preferences)

    plan = await ainvoke_json(
        _build_prompt(request, dates, weather_lines, candidates),
        TripPlan,
        system=PLAN_SYSTEM_PROMPT,
    )

    # 审计兜底：模型可能没听「雨天不排户外」，这里逐条改掉
    plan, adjustments = audit_plan(plan, weather_by_date, candidates["indoor"])

    return {
        "request": request.model_dump(),
        "dates": dates,
        "weather": weather_by_date,
        "plan": plan.model_dump(),
        "adjustments": adjustments,
    }


def plan_to_itinerary_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    """把行程草案转成可写入行程表的条目（供「一键保存」用）。

    只做字段映射、不落库——落库交给 itinerary_service，
    让这个 Skill 保持「纯生成」，不掺数据库副作用。
    """
    items: list[dict[str, Any]] = []
    for day in (result.get("plan") or {}).get("plan", []):
        date_str = day.get("date")
        for entry in day.get("items", []):
            title = (entry.get("title") or "").strip()
            if not date_str or not title:
                continue
            items.append(
                {
                    "date": date_str,
                    "title": title[:255],
                    "start_time": (entry.get("time") or "").strip()[:5] or None,
                    "location": title[:128],
                    "activity": (entry.get("activity") or "").strip()[:64] or None,
                    "note": (entry.get("reason") or "").strip() or None,
                }
            )
    return items


def render_text(result: dict[str, Any]) -> str:
    """把结果渲染成对话里可读的文本（Agent 工具用）。"""
    plan = result.get("plan") or {}
    request = result.get("request") or {}
    lines = [f"【{plan.get('city', request.get('city'))} {plan.get('days')} 天行程】"]
    if plan.get("summary"):
        lines.append(plan["summary"])

    for day in plan.get("plan", []):
        weather = result.get("weather", {}).get(day.get("date"), {})
        header = f"\n{day.get('date')}　{weather.get('desc', '')}"
        if weather.get("needs_indoor"):
            header += "（不适合户外）"
        lines.append(header)
        if day.get("weather_note"):
            lines.append(f"  ⚠️ {day['weather_note']}")
        for entry in day.get("items", []):
            mark = "（已因天气调整）" if entry.get("weather_adjusted") else ""
            lines.append(
                f"  {entry.get('time', '')} {entry.get('title', '')}"
                f"　{entry.get('activity', '')}{mark}"
            )
            if entry.get("reason"):
                lines.append(f"      {entry['reason']}")

    if result.get("adjustments"):
        lines.append("\n已按天气做的调整：")
        lines.extend(f"  - {item}" for item in result["adjustments"])

    lines.append("\n如需保存，可在「智能推荐 → AI 排行程」里一键写入我的行程。")
    return "\n".join(lines)


async def run(query: str) -> str:
    """Agent 工具入口：排一份行程并返回可读文本。"""
    result = await generate(query)
    return render_text(result)
