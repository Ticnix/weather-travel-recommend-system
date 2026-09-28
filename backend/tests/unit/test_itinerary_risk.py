"""行程 × 天气冲突扫描的单测（Day 51）。

全部只测**纯函数**（`assess_day` / `scan_items` / `pick_alternative` / `build_advice`），
不碰数据库也不碰网络——规则这类东西必须能脱离环境反复验证，
否则改一个阈值就要起一整套容器。

用真实的 `DailyForecast` 而不是假对象：字段被改名时这里会直接失败，
而 `MagicMock` 不会。
"""

from __future__ import annotations

from app.services.itinerary_risk import (
    assess_day,
    build_advice,
    is_indoor,
    pick_alternative,
    scan_items,
    score_day,
)
from app.services.weather_client import DailyForecast

TODAY = "2026-09-23"


def day(
    date: str,
    *,
    desc: str | None = "多云",
    tmax: float | None = 30.0,
    tmin: float | None = 24.0,
    precip: float | None = 0.0,
    wind: float | None = 10.0,
) -> DailyForecast:
    return DailyForecast(
        date=date,
        temp_max=tmax,
        temp_min=tmin,
        precipitation_sum=precip,
        wind_speed_max=wind,
        weather_code=None,
        weather_desc=desc,
        sunrise=None,
        sunset=None,
    )


def item(**over) -> dict:
    base = {
        "id": 1,
        "user_id": 2,
        "title": "白云山爬山",
        "date": TODAY,
        "start_time": "09:00",
        "location": "白云山",
        "activity": "爬山",
    }
    base.update(over)
    return base


# ===== assess_day：规则 =====


def test_雷阵雨按描述判定_即使日累计降水很小():
    """核心用例：雷阵雨常常一阵就过，日累计可能只有 0.9mm。

    如果只按降水阈值判，这种最该提醒的情况反而会被漏掉
    （Day 29 的测试就抓出过同类缺陷）。
    """
    hit = assess_day(day(TODAY, desc="雷阵雨", precip=0.9), None)
    assert hit is not None
    assert hit.kind == "rain"
    assert hit.level == "danger"
    assert "雷阵雨" in hit.reason


def test_暴雨级别更高():
    assert assess_day(day(TODAY, desc="暴雨", precip=30), None).level == "danger"


def test_降水达到阈值提示_超过25mm升级为危险():
    assert assess_day(day(TODAY, desc="中雨", precip=12), None).level == "warn"
    assert assess_day(day(TODAY, desc="大雨", precip=26), None).level == "danger"


def test_晴天不报():
    assert assess_day(day(TODAY, desc="晴", precip=0), None) is None


def test_大风按阈值或描述判定():
    assert assess_day(day(TODAY, wind=45), None).kind == "wind"
    assert assess_day(day(TODAY, desc="大风", wind=20), None).kind == "wind"
    assert assess_day(day(TODAY, desc="多云", wind=20), None) is None


def test_高温只对户外活动成立():
    hot = day(TODAY, desc="晴", tmax=36.0)
    assert assess_day(hot, None, indoor=False).kind == "heat"
    # 室内安排（博物馆/商场…）不受高温影响，不该打扰用户
    assert assess_day(hot, None, indoor=True) is None


def test_降温需要前一天数据_缺数据时不猜():
    today_cool = day(TODAY, desc="多云", tmax=24.0)
    assert assess_day(today_cool, day("2026-09-22", tmax=33.0), ).kind == "drop"
    # 拿不到前一天 → 不产生结论（而不是默认安全或默认危险）
    assert assess_day(today_cool, None) is None


def test_室内活动识别():
    assert is_indoor("博物馆", None, None) is True
    assert is_indoor("爬山", "白云山", None) is False
    # 判断不出来时按户外处理（保守）
    assert is_indoor(None, "约朋友", None) is False


# ===== scan_items：窗口与缺数据行为 =====


def test_预报缺失时不误报():
    """检查清单明确要求：没有预报数据时不能当成晴天，也不能乱报风险。"""
    hits = scan_items([item(date=TODAY)], {}, today=TODAY)
    assert hits == []


def test_扫描窗口外的行程不看():
    """3 天以后的行程既没有可信预报，提醒也太早。"""
    far = "2026-09-30"
    forecast = {far: day(far, desc="暴雨", precip=40)}
    assert scan_items([item(date=far)], forecast, today=TODAY) == []


def test_过去的行程不看():
    past = "2026-09-20"
    forecast = {past: day(past, desc="暴雨", precip=40)}
    assert scan_items([item(date=past)], forecast, today=TODAY) == []


def test_命中时带上可执行建议_推荐更好的日子():
    forecast = {
        TODAY: day(TODAY, desc="雷阵雨", precip=12),
        "2026-09-24": day("2026-09-24", desc="多云", tmax=29, tmin=23, precip=0),
    }
    hits = scan_items([item()], forecast, today=TODAY)
    assert len(hits) == 1
    assert hits[0]["level"] == "danger"
    # 建议里要出现"改到 09-24"，否则用户只知道不能去、不知道什么时候能去
    assert "09-24" in hits[0]["body"]
    assert hits[0]["date"] == TODAY


def test_没有更好的日子时说明都不合适():
    forecast = {
        TODAY: day(TODAY, desc="暴雨", precip=40),
        "2026-09-24": day("2026-09-24", desc="雷阵雨", precip=15),
    }
    hits = scan_items([item()], forecast, today=TODAY)
    assert len(hits) == 1
    assert "改到" not in hits[0]["body"]
    assert "室内" in hits[0]["body"] or "顺延" in hits[0]["body"]


def test_多条行程各自判定():
    forecast = {TODAY: day(TODAY, desc="雷阵雨", precip=12)}
    items = [
        item(id=1, title="爬山", activity="爬山"),
        item(id=2, title="逛博物馆", activity="博物馆"),
    ]
    hits = scan_items(items, forecast, today=TODAY)
    # 暴雨对室内活动同样影响出行，两条都该报（但原因说明不同场景）
    assert [h["itinerary_id"] for h in hits] == [1, 2]


# ===== pick_alternative / score_day =====


def test_打分偏好无雨与舒适温度():
    good = score_day(day("2026-09-24", desc="多云", tmax=27, tmin=22, precip=0))
    worse = score_day(day("2026-09-25", desc="多云", tmax=34, tmin=28, precip=2))
    assert good is not None and worse is not None
    assert good < worse


def test_有明显降水的日子不作为候选():
    assert score_day(day("2026-09-24", desc="暴雨", precip=30)) is None
    assert score_day(day("2026-09-24", desc="多云", precip=15)) is None


def test_建议的候选必须晚于今天():
    forecast = {
        "2026-09-21": day("2026-09-21", desc="晴", tmax=27, tmin=22),  # 已经过去
        "2026-09-25": day("2026-09-25", desc="晴", tmax=27, tmin=22),
    }
    alt = pick_alternative(forecast, TODAY, TODAY)
    assert alt is not None
    assert alt.date == "2026-09-25"  # 不能建议用户"改到昨天"


def test_建议文案包含地点与时间():
    hit = assess_day(day(TODAY, desc="雷阵雨", precip=12), None)
    title, body = build_advice(item(), hit, None)
    assert "白云山" in title
    assert "09:00" in body
    assert "白云山" in body
