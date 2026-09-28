"""法定节假日日历：把「国庆」「中秋」这类说法落成具体日期与放假天数。

需求里最常见的日期说法不是「10 月 1 日」，而是「国庆」「中秋」。
不认这些词，日期就会静默回落到"今天"；认了、却只给两三天，
又会把 7 天长假排成三天两夜——两个都是用户一眼就能看出来的错。

所以这里回答两件事：
1. **从哪天开始**：国庆 = 10-01、中秋 = 农历八月十五、春节 = 除夕
2. **法定放几天**：国庆 7 天、五一 5 天、春节 8 天、元旦/清明/端午/中秋 3 天

为什么用本地规则而不是在线节假日接口：
网上确实有免费接口（timor.tech、jiejiariapi 等），但它们是第三方服务、
没有任何可用性承诺；而且"调休安排"要等国务院当年通知，**未来年份本来就不存在**。
排程是核心链路，不该被一个外部服务卡住。本地规律给出的"起始日 + 假期长度"
已经能回答用户真正关心的"玩几天"；调休里"哪几天要上班"不影响出行安排。
（若将来要精确到调休，可在此加一个带超时+缓存的接口实现，
失败时仍然回落到下面的本地规则即可。）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

try:  # 农历换算：纯 Python 小库（1900-2099），无传递依赖
    from lunardate import LunarDate
except ImportError:  # pragma: no cover - 缺依赖时只是不认农历节日，公历节日照常
    LunarDate = None


@dataclass(frozen=True)
class Festival:
    """一个法定节假日。"""

    name: str  # 规范名，也是返回给用户的说法
    days: int  # 法定放假天数（含周末与调休）
    aliases: tuple[str, ...] = ()
    month: int | None = None  # 公历节日的月
    day: int | None = None  # 公历节日的日
    lunar: tuple[int, int] | None = None  # 农历节日的 (月, 日)
    start_offset: int = 0  # 相对锚点的天数偏移（春节从除夕起算 → -1）
    is_solar_term: bool = False  # 清明是节气，日期逐年浮动，需按公式算


FESTIVALS: tuple[Festival, ...] = (
    Festival("元旦", 3, month=1, day=1),
    # 春节假期含除夕，从除夕开始连休（2025 起为 8 天）
    Festival("春节", 8, lunar=(1, 1), start_offset=-1, aliases=("过年", "农历新年")),
    Festival("清明", 3, month=4, day=4, is_solar_term=True, aliases=("清明节",)),
    Festival("劳动节", 5, month=5, day=1, aliases=("五一",)),
    Festival("端午", 3, lunar=(5, 5), aliases=("端午节",)),
    Festival("中秋", 3, lunar=(8, 15), aliases=("中秋节", "团圆节")),
    Festival("国庆", 7, month=10, day=1, aliases=("国庆节", "十一")),
)


def _keywords(festival: Festival) -> tuple[str, ...]:
    return (festival.name, *festival.aliases)


# 匹配顺序：长词优先，避免「国庆节」被「国庆」抢先（结果一样，但说明话术要准）
_MATCH_ORDER: tuple[Festival, ...] = tuple(
    sorted(FESTIVALS, key=lambda item: -max(len(word) for word in _keywords(item)))
)


def _qingming(year: int) -> date:
    """清明节气日期（20~21 世纪近似公式，误差 ±1 天，排程够用）。"""
    short = year % 100
    return date(year, 4, int(short * 0.2422 + 4.81) - int(short / 4))


def _lunar_to_solar(year: int, month: int, day: int) -> date | None:
    """农历 → 公历；库未安装或日期非法时返回 None。"""
    if LunarDate is None:
        return None
    try:
        lunar = LunarDate(year, month, day)
        # 0.2.2 起推荐 to_solar_date，旧版本只有 toSolarDate
        convert = getattr(lunar, "to_solar_date", None) or lunar.toSolarDate
        return convert()
    except Exception:  # noqa: BLE001 闰月等非法组合
        return None


def _anchor(festival: Festival, year: int) -> date | None:
    """节假日的锚点日期（春节为除夕）。"""
    if festival.is_solar_term:
        return _qingming(year)
    if festival.lunar:
        return _lunar_to_solar(year, *festival.lunar)
    if festival.month and festival.day:
        try:
            return date(year, festival.month, festival.day)
        except ValueError:  # 2 月 30 日这类不存在的日期
            return None
    return None


def find_festival(text: str) -> Festival | None:
    """找出需求里提到的节假日。"""
    raw = text or ""
    if not raw:
        return None
    for festival in _MATCH_ORDER:
        for word in _keywords(festival):
            if word == "十一":
                # 必须排除「十一月」：否则"十一月去广州"会被排到国庆
                if re.search(r"十一(?!月)", raw):
                    return festival
            elif word in raw:
                return festival
    return None


def festival_start(festival: Festival, ref: date) -> date | None:
    """不早于 ref 的最近一次假期起始日；跨年节日（元旦/春节）自动落到明年。"""
    for year in (ref.year, ref.year + 1):
        anchor = _anchor(festival, year)
        if anchor is None:
            continue
        start = anchor + timedelta(days=festival.start_offset)
        if start >= ref:
            return start
    return None


def resolve(text: str, ref: date) -> tuple[Festival, date] | None:
    """需求 → (节假日, 起始日)；需求里没提节假日、或算不出日期时返回 None。

    ref 是"今天"，用来把"今年已过"的节假日落到明年——春节这种跨年节日尤其需要。
    """
    festival = find_festival(text)
    if festival is None:
        return None
    start = festival_start(festival, ref)
    if start is None:
        return None
    return festival, start


def holiday_days(text: str) -> int | None:
    """需求里提到的节假日的法定放假天数；没提则 None。"""
    festival = find_festival(text)
    return festival.days if festival else None
