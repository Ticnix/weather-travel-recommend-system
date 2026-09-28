"""AI 一键排行程 Skill（Day 40）。

输入「想去哪 / 几天 / 偏好」，输出**可直接保存到行程表**的结构化行程。

编排链：
 1. 解析需求   → 城市 / 区域 / 日期 / 天数 / 偏好   parse_request（纯函数）
 2. 查天气     → 每天是否适合户外                  needs_indoor（纯函数）
 3. 找候选景点 → amap place/text（按区域取，带所在区）（有 Key 走高德，无 Key 回落内置地标）
 4. 交 LLM     → 结构化行程                        llm_client.ainvoke_json
 5. 审计并纠正 → 雨天不排户外                      audit_plan（纯函数）

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

from app.services import amap_client, holiday_calendar
from app.services.city_dict import all_supported_cities, lookup_city
from app.services.district_dict import area_core, cities_of, match_area
from app.services.llm_client import ainvoke_json
from app.services.weather_service import fetch_weather

logger = logging.getLogger(__name__)

DEFAULT_CITY = "广州"
DEFAULT_DAYS = 2
# 上限必须放得下"最长的法定假期"（国庆 7 天、春节 8 天）。
# 原先是 5，于是"国庆去玩几天"最多只能排 5 天——长假被砍短，用户一眼就看出来。
MAX_DAYS = 10

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

# 星期几 → weekday()（周一起算）
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

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
    # 坐标**不由模型生成**（模型只会编），而是生成后从候选 POI 里按名字反查补上，
    # 供前端"点地点名 → 打开地图看位置"。查不到就是 None，前端退回按地名搜索。
    lng: float | None = Field(default=None, description="经度（来自候选 POI，非模型生成）")
    lat: float | None = Field(default=None, description="纬度（来自候选 POI，非模型生成）")


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
    # 出发日期（YYYY-MM-DD）：需求里没提日期时为 None，由调用方回落「今天」。
    # 单独存字段而不是只用在内部计算，是为了让前端能显示"排的是哪天"。
    start_date: str | None = None
    date_hint: str | None = None  # 命中的日期原词（如「国庆」），用于向用户说明依据
    # 需求里写的市辖区（如「南沙区」）：有值时候选景点只在区内取，
    # 因为"用户写了区却拿到全城行程"是最初实际踩到的坑。
    area: str | None = None
    area_hint: str | None = None  # 命中的区域原词（如「南沙」）


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


def _upcoming(ref: date, month: int, day: int) -> date | None:
    """把「某月某日」落到不早于 ref 的最近一次（今年过了就算明年）。"""
    for year in (ref.year, ref.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:  # 2 月 30 日这类不存在的日期
            continue
        if candidate >= ref:
            return candidate
    return None


def parse_start_date(text: str, ref: date) -> tuple[date | None, str | None]:
    """解析出发日期，返回 (日期, 命中的原词)；解析不出返回 (None, None)。

    ref 是「今天」，用它把相对说法（明天/周末/下周）落成具体日期。

    把命中的原词一并返回，是因为「默默换掉用户说的日期」和「默默换掉城市」
    属于同一类错误：用户写了国庆，就该看到"已按国庆（10-01）排"，
    而不是拿到一份从今天开始的行程，还以为 AI 没看懂他说的日期。
    """
    raw = (text or "").strip()
    if not raw:
        return None, None

    for keyword in ("今天", "今日"):
        if keyword in raw:
            return ref, keyword
    if "后天" in raw:
        return ref + timedelta(days=2), "后天"
    for keyword in ("明天", "明日"):
        if keyword in raw:
            return ref + timedelta(days=1), keyword

    # 周末 → 最近的周六（今天就是周六则从今天算起）
    saturday_offset = (5 - ref.weekday()) % 7
    if "下周末" in raw:
        return ref + timedelta(days=saturday_offset + 7), "下周末"
    if "周末" in raw:
        return ref + timedelta(days=saturday_offset), "周末"

    # 下周X / 下个星期X → 先跳到下周一，再按星期几偏移
    matched = re.search(r"下(?:个)?(?:周|星期)([一二三四五六日天])?", raw)
    if matched:
        next_monday = ref + timedelta(days=(7 - ref.weekday()) % 7 or 7)
        weekday = matched.group(1)
        if weekday:
            return next_monday + timedelta(days=_WEEKDAYS[weekday]), matched.group(0)
        return next_monday, matched.group(0)

    # 明确写了几月几号
    matched = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", raw)
    if matched:
        target = _upcoming(ref, int(matched.group(1)), int(matched.group(2)))
        if target:
            return target, matched.group(0)

    # 节假日（国庆/中秋/春节…）交给 holiday_calendar：
    # 农历节日（中秋/春节/端午）无法用固定公历日期表示，只能换算；
    # 顺带把"今年已过就落到明年"也由它处理。
    resolved = holiday_calendar.resolve(raw, ref)
    if resolved:
        festival, start = resolved
        return start, festival.name

    return None, None


def parse_days(text: str, ref: date | None = None) -> int:
    """从自然语言里解析天数（超过上限按上限截断）。

    要同时认「天」和「日」：「三日游」「两日游」是极常见的说法，
    只认「天」的话这些话会被当成没提天数，静默用默认值——
    用户拿到一个 2 天行程却说自己要 3 天，是最容易被忽略的一类错。

    ref 是"今天"，用于判断"只说了某一天"（明天 / 10月1号 / 下周五）。
    那种情况下天数是 **1 天**：用户说的是"明天给我安排一个行程"，
    给他排两天等于凭空多塞一天，他只会觉得"它没听懂"。
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

    # 提了节假日却只说「玩几天」：按这个假期的**法定天数**给（国庆 7 天、五一 5 天、
    # 中秋 3 天），别把长假排成两天一夜。注意顺序——上面已先认显式天数，
    # 所以"国庆玩5天"仍是 5 天，用户说了算；也要在下面的"单个日期"之前，
    # 否则"国庆去玩几天"会被当成只玩一天。
    holiday = holiday_calendar.holiday_days(text)
    if holiday:
        return min(holiday, MAX_DAYS)

    # 只说了某一天、没说玩几天 → 就是一天
    if ref is not None and parse_start_date(text, ref)[0] is not None:
        return 1

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


def parse_request(query: str, ref: date | None = None) -> TripRequest:
    """把一句自然语言需求解析成结构化请求。

    ref 是作为「今天」的参照日，默认取系统当天；显式传入是为了让
    「国庆」「周末」这类相对日期在测试里可复现（不随运行日期漂移）。
    """
    text = (query or "").strip()
    city, assumed = parse_city(text)

    matched = match_area(text)
    area, area_hint = matched if matched else (None, None)
    if area:
        # 区名能唯一确定城市时，就不该再说"没听出你想去哪个城市"：
        # 「去南沙区玩」里的南沙区只属于广州，这已经足够回答城市问题了。
        owners = cities_of(area)
        if len(owners) == 1 and owners[0] in all_supported_cities():
            city, assumed = owners[0], False

    today = ref or date.today()
    start, hint = parse_start_date(text, today)
    return TripRequest(
        city=city,
        days=parse_days(text, today),
        preferences=parse_preferences(text),
        city_assumed=assumed,
        start_date=start.isoformat() if start else None,
        date_hint=hint,
        area=area,
        area_hint=area_hint,
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


# 偏好标签 → 高德 POI 类型码；没对应的按"风景名胜"搜（博物馆/公园/古镇都归在里面）
_POI_TYPES_BY_PREF: dict[str, str] = {
    "美食": amap_client.POI_FOOD,
    "购物": amap_client.POI_SHOPPING,
}
_POI_TYPE_DEFAULT = amap_client.POI_SCENERY

# 单个关键词取多少条 POI：区域过滤会筛掉一部分，多取一点才够用
_POI_PER_QUERY = 10


def _search_pairs(categories: list[str], core: str | None) -> list[tuple[str, str]]:
    """生成 (关键词, 类型码) 检索组合。

    限定区域时关键词用**区名本身**，而不是「南沙景点」这类拼接词：
    高德的关键词是字面匹配，拼接词只会命中少数小地方（实测「南沙景点」
    返回的全是东涌的村口公园），而「南沙」+ 类型过滤能稳定拿到
    天后宫、水鸟世界、湿地公园这些真正的景点。
    """
    types_of = [_POI_TYPES_BY_PREF.get(category, _POI_TYPE_DEFAULT) for category in categories]
    if core:
        # 关键词都是区名，只有类型不同，去重后逐个类型查一次
        return [(core, types) for types in dict.fromkeys(types_of)]
    return list(zip(categories, types_of))


def _poi_in_area(poi: dict[str, Any], core: str) -> bool:
    """判断 POI 是否落在目标区域内。

    只看 adname 不够：搜「东涌镇」时 adname 只有"南沙区"，镇名藏在 address 里；
    但**不能看名称**——「蒙奇D寿司店(南沙店)」这种店名带"南沙"的分店可能开在市区的
    另一个区，按名字匹配会把区外地点放进来，而"说了南沙却排到越秀"正是要修的问题。
    """
    located = f"{poi.get('district', '')}{poi.get('address', '')}"
    if located:
        return core in located
    return core in poi.get("name", "")  # 少数 POI 没有行政区信息时只能退回看名称


# 明显不是"可安排的地点"的 POI 分类前缀（住宅小区、公司、生活服务网点…）
_POI_SKIP_TYPE_PREFIXES = ("商务住宅", "公司企业", "生活服务", "政府机构", "地名地址")

# 名称里带这些词的也不是能"安排去玩"的地方。（少数真叫"XX民居"的景点会被一起滤掉，
# 但宁可少一个候选，也不要出现"行程：莲溪大街78号民居"这种让用户发愣的安排。）
_POI_SKIP_NAME_KEYWORDS = ("民居", "小区", "公寓", "宿舍", "办事处", "批发", "建材", "五金")


def _is_place_of_interest(poi: dict[str, Any]) -> bool:
    """过滤掉检索结果里的非景点（住宅区/公司/办事处/民居）。

    高德的"风景名胜"大类里混着「XX民居」「XX雅苑」这类条目，
    直接塞给模型就会排进行程，用户看到"行程：莲溪大街78号民居"只会觉得莫名其妙。
    分类过滤挡不住名字型的噪音（它们被归到了"风景名胜"下），所以名称也要看一眼。
    """
    if (poi.get("type") or "").startswith(_POI_SKIP_TYPE_PREFIXES):
        return False
    return not any(word in poi.get("name", "") for word in _POI_SKIP_NAME_KEYWORDS)


async def _search_pois(
    city: str, categories: list[str], core: str | None
) -> list[dict[str, Any]]:
    """按 (关键词, 类型) 组合检索并合并候选 POI。"""
    found: list[dict[str, Any]] = []
    for keyword, types in _search_pairs(categories, core):
        try:
            pois = await amap_client.search_pois(
                keyword, city=city, types=types, limit=_POI_PER_QUERY
            )
        except Exception as exc:  # noqa: BLE001 检索失败不该让整个排程挂掉
            logger.warning("景点检索失败 keyword=%s: %s", keyword, exc)
            continue
        if core:
            pois = [poi for poi in pois if _poi_in_area(poi, core)]
        found.extend(poi for poi in pois if _is_place_of_interest(poi))
    return found


async def collect_candidates(
    city: str, preferences: list[str], area: str | None = None, limit: int = 15
) -> dict[str, Any]:
    """收集候选景点，分成室内 / 户外两组。

    数据来源优先高德 POI 检索；无 Key 时 amap_client 会回落内置地标库，
    再拿不到就用一组通用兜底——保证 LLM 至少有东西可排，不至于空手而归。

    指定区域（「南沙区」）时只取该区内的地点：用户写了区，就不该收到
    一份越秀/北京路的行程。区内确实搜不到时回落全城，并用
    area_matched=False 让前端把这件事说出来，而不是悄悄换地方。
    """
    core = area_core(area) if area else None
    categories = list(dict.fromkeys(["景点", *preferences]))

    pois = await _search_pois(city, categories, core)
    area_matched = bool(core)
    if core and not pois:
        logger.info("区域 %s 内没检索到候选景点，回落 %s 全城", area, city)
        pois = await _search_pois(city, categories, None)
        area_matched = False

    unique = list(dict.fromkeys(poi["name"] for poi in pois if poi.get("name")))
    if not unique:
        unique = [f"{city}博物馆", f"{city}人民公园"]

    indoor = [name for name in unique if not is_outdoor(name)]
    outdoor = [name for name in unique if is_outdoor(name)]
    return {
        "indoor": indoor[:limit],
        "outdoor": outdoor[:limit],
        "all": unique[:limit],
        "area_matched": area_matched,
        # 名字 → 坐标：生成行程后按名字反查，给前端"点开地图"用
        "coords": {
            poi["name"]: {"lng": poi["lng"], "lat": poi["lat"]}
            for poi in pois
            if poi.get("name") and poi.get("lng") is not None
        },
    }


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
7. 指定了「区域」时，所有地点都必须落在该区域内——宁可少排几项，也不要跨区
"""


def _build_prompt(
    request: TripRequest,
    dates: list[str],
    weather_lines: list[str],
    candidates: dict[str, Any],
) -> str:
    """拼装排程提示词：把「约束」交给模型，把「校验」留给自己。"""
    preferences = "、".join(request.preferences) if request.preferences else "无特别偏好"
    weather_text = "\n".join(weather_lines) if weather_lines else "（天气数据不可用）"
    indoor = "、".join(candidates["indoor"]) if candidates["indoor"] else "（无）"
    outdoor = "、".join(candidates["outdoor"]) if candidates["outdoor"] else "（无）"
    # 区域是硬约束：候选景点已按区取好，这里再写一遍是防止模型自己"加戏"跨区
    area_line = f"区域：{request.area}（所有地点必须在{request.area}内）\n" if request.area else ""
    holiday_note = f"（{request.date_hint}假期）" if request.date_hint else ""

    return f"""请为以下需求排一份 {request.days} 天行程。

城市：{request.city}
{area_line}日期：{"、".join(dates)}{holiday_note}
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


def weather_hint(dates: list[str], weather_by_date: dict[str, dict[str, Any]]) -> str | None:
    """日期超出预报范围时，明确告知「本次没有天气约束」。

    天气预报只有未来 7 天左右，而用户很可能排的是国庆这种远期行程。
    不说明的话，他看到某天没有天气标签会以为功能坏了；
    而「没做雨天规避」和「排了户外但预报是晴天」是两件完全不同的事，
    不能都表现为"那一栏空着"。
    """
    if not dates:
        return None
    missing = [date_str for date_str in dates if date_str not in weather_by_date]
    if not missing:
        return None
    if len(missing) == len(dates):
        return "所选日期暂无天气预报（超出预报范围），本次未做雨天规避，出行前请再确认天气"
    return f"{'、'.join(missing)} 暂无天气预报，这些日期未做雨天规避"


def attach_coordinates(plan: TripPlan, coords: dict[str, dict[str, float]]) -> int:
    """给行程条目补上坐标，返回补上的条数（前端据此决定能不能直接定位）。

    坐标**不交给模型生成**：模型编出来的经纬度看起来很像真的，但错得离谱，
    而"点开地图发现位置不对"比"点了没反应"更伤信任。
    这里改成从候选 POI 里按名字反查——提示词本就要求只用候选地点，
    所以多数条目能命中；命不中的（如「XX 附近用餐」）留空，
    前端退回"按地名搜索"，绝不猜一个坐标出来。
    """
    filled = 0
    for day in plan.plan:
        for item in day.items:
            point = coords.get(item.title)
            if point is None:
                # 模型有时会保留主干、改掉括号里的店名后缀，允许包含匹配兜一下
                point = next(
                    (
                        value
                        for name, value in coords.items()
                        if name and (name in item.title or item.title in name)
                    ),
                    None,
                )
            if point is None:
                continue
            item.lng = float(point["lng"])
            item.lat = float(point["lat"])
            filled += 1
    return filled


def _area_note(request: TripRequest, candidates: dict[str, Any]) -> str | None:
    """区域没检索到候选地点时的说明；正常命中返回 None。

    和 weather_hint 同一个理由：**"没做到"必须说出来**。
    用户写了南沙区，如果最后拿到的是全城行程又不加说明，
    他只会得出"我说了跟没说一样"的结论。
    """
    if not request.area or candidates.get("area_matched", True):
        return None
    return (
        f"「{request.area}」内没检索到候选地点，本次已按{request.city}全城规划——"
        f"出行前请再核对地点是否都在{request.area}"
    )


async def generate(query: str, today: date | None = None) -> dict[str, Any]:
    """完整排程链路：解析 → 天气 → 候选 → LLM → 审计。"""
    ref = today or date.today()
    request = parse_request(query, ref)
    # 用户写了「国庆」「周末」就按那个日期排，没写才从今天起算。
    # 这里原先直接写 date.today()，于是"国庆去广州"排出来的还是今明两天。
    start = date.fromisoformat(request.start_date) if request.start_date else ref
    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(request.days)]

    weather_by_date, weather_lines = await _collect_weather(request.city, dates)
    # 区域一起传下去：候选景点只在区内取（「南沙区」不该排到越秀）
    candidates = await collect_candidates(request.city, request.preferences, request.area)

    plan = await ainvoke_json(
        _build_prompt(request, dates, weather_lines, candidates),
        TripPlan,
        system=PLAN_SYSTEM_PROMPT,
    )

    # 审计兜底：模型可能没听「雨天不排户外」，这里逐条改掉
    plan, adjustments = audit_plan(plan, weather_by_date, candidates["indoor"])

    # 坐标放在审计之后补：审计会把户外项换成室内候选，换完再反查坐标才对得上
    attach_coordinates(plan, candidates.get("coords", {}))

    return {
        "request": request.model_dump(),
        "dates": dates,
        "weather": weather_by_date,
        "weather_hint": weather_hint(dates, weather_by_date),
        "area_note": _area_note(request, candidates),
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
