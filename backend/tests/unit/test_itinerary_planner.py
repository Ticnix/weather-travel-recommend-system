"""AI 一键排行程测试（Day 40）。

**为什么这些用例能脱离 LLM 跑**：排程本身依赖模型（不稳定、测不了），
但「需求解析」与「天气审计」被刻意抽成了纯函数——
而这两块恰好是唯一可能出错、也唯一必须保证的地方。

最关键的断言只有一句：**审计之后，坏天气的日期里不允许再出现户外安排**。
这就是检查清单里「行程与真实天气不冲突」的真正含义。
"""

from datetime import date
from typing import ClassVar

import pytest

from skills.itinerary_planner.scripts import planner


def _plan(days: list[tuple[str, list[tuple[str, str, str]]]]) -> planner.TripPlan:
    """造一份行程：[(日期, [(时间, 地点, 活动)])]"""
    return planner.TripPlan(
        city="广州",
        days=len(days),
        summary="测试用",
        plan=[
            planner.PlanDay(
                date=date,
                items=[
                    planner.PlanItem(time=time, title=title, activity=activity)
                    for time, title, activity in items
                ],
            )
            for date, items in days
        ],
    )


class TestParseRequest:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("周末想去广州玩两天", 2),
            ("去上海玩3天", 3),
            ("帮我排个三日游", 3),
            ("想玩五天", 5),
            ("排个十天行程", 10),  # 上限提到 10：要放得下国庆 7 天、春节 8 天
            ("排个二十天行程", 10),  # 超上限按上限截断
            ("随便逛逛", 2),  # 没提天数用默认
        ],
    )
    def test_解析天数(self, text, expected):
        assert planner.parse_days(text) == expected

    def test_解析城市(self):
        assert planner.parse_city("想去上海玩") == ("上海", False)

    def test_识别不出城市时标注为推断(self):
        city, assumed = planner.parse_city("随便找个地方玩两天")
        assert city == planner.DEFAULT_CITY
        # 必须标注是推断值：默默给出另一个城市的行程，比问一句更糟
        assert assumed is True

    def test_解析偏好可命中多个(self):
        prefs = planner.parse_preferences("想吃美食，也喜欢拍照和爬山")
        assert "美食" in prefs
        assert "拍照" in prefs

    def test_解析完整需求(self):
        request = planner.parse_request("周末想去广州玩两天，喜欢美食")
        assert request.city == "广州"
        assert request.days == 2
        assert "美食" in request.preferences
        assert request.city_assumed is False

    def test_只提节假日时天数按该节假日的法定天数(self):
        # "国庆去广州玩几天"里的「几」不是数字：不能静默当成 2 天一夜，
        # 更不能把 7 天长假排成两三天——用户一眼就能看出少了
        assert planner.parse_days("国庆去广州玩几天") == 7
        assert planner.parse_days("十一想去广州") == 7
        assert planner.parse_days("五一去广州") == 5
        assert planner.parse_days("中秋去广州玩几天") == 3

    def test_节假日同时写明天数时以天数优先(self):
        assert planner.parse_days("国庆去广州玩5天") == 5

    @pytest.mark.parametrize(
        "text",
        [
            "明天给我安排一个行程",  # 用户实际踩到的坑：排成了两天
            "明天去广州玩",
            "10月1号去广州",
            "下周五去广州",
            "后天去广州逛逛",
        ],
    )
    def test_只说了某一天就是一天行程(self, text):
        # 说了具体某天又没说玩几天 → 1 天；默认 2 天等于凭空多塞一天
        assert planner.parse_days(text, date(2026, 9, 18)) == 1

    def test_没提日期时仍用默认天数(self):
        # 既没日期也没天数时保持原样，不要因为上面的规则把默认值改掉
        assert planner.parse_days("去广州玩", date(2026, 9, 18)) == planner.DEFAULT_DAYS
        assert planner.parse_days("随便逛逛", date(2026, 9, 18)) == planner.DEFAULT_DAYS

    def test_解析需求带出发日期(self):
        request = planner.parse_request("国庆去广州玩3天", date(2026, 9, 18))
        assert request.start_date == "2026-10-01"
        assert request.date_hint == "国庆"

    def test_没提日期时start_date为空(self):
        # 为空表示"从今天起算"，由 generate 兜底——而不是在这里瞎猜一个日期
        assert planner.parse_request("去广州玩两天", date(2026, 9, 18)).start_date is None


class TestParseArea:
    """「说了南沙区却排到越秀」是实际踩到的第二个坑：区域必须被解析并用于取数。"""

    def test_识别市辖区全称(self):
        assert planner.match_area("跟男朋友中秋去南沙区玩，喜欢吃东西和看落日") == (
            "南沙区",
            "南沙区",
        )

    def test_区名简称也能识别(self):
        area, hint = planner.match_area("周末去南沙玩两天")
        assert area == "南沙区"
        assert hint == "南沙"  # 原词要留给前端说明依据

    @pytest.mark.parametrize(
        "text",
        [
            "想去白云山爬山",  # 白云山不是白云区
            "逛海珠广场",
            "去天河城买东西",  # 天河城不是天河区
            "这个地区随便走走两天",  # 句子片段不是行政区名
        ],
    )
    def test_具体地点与句子片段不会被当成行政区(self, text):
        assert planner.match_area(text) is None

    def test_区名能反推城市(self):
        # 南沙区只属于广州：不该再提示"没听出你想去哪个城市"
        request = planner.parse_request("中秋去南沙区玩，喜欢吃东西", date(2026, 9, 18))
        assert request.area == "南沙区"
        assert request.city == "广州"
        assert request.city_assumed is False

    def test_没写区域时区域为空(self):
        assert planner.parse_request("去广州玩两天").area is None


class TestHolidayCalendar:
    """节假日：起始日 + 法定天数。农历节日必须换算，不能硬编公历日期。"""

    REF: ClassVar[date] = date(2026, 9, 18)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("国庆去广州玩几天", "2026-10-01"),
            ("中秋去南沙区玩", "2026-09-25"),  # 农历八月十五
            ("五一去广州", "2027-05-01"),  # 今年五一已过 → 落到明年
            ("元旦去哈尔滨", "2027-01-01"),  # 跨年节日
        ],
    )
    def test_节假日起始日(self, text, expected):
        start, _hint = planner.parse_start_date(text, self.REF)
        assert (start.isoformat() if start else None) == expected

    def test_春节从除夕开始(self):
        start, hint = planner.parse_start_date("春节想去广州", self.REF)
        # 除夕是"想回家过年"的真正起点：只按正月初一会少一天
        assert hint == "春节"
        assert start is not None
        assert planner.holiday_calendar.resolve("春节", self.REF)[1] == start

    def test_缺农历依赖时公历节日仍然可用(self, monkeypatch):
        # lunardate 是唯一新增依赖：万一没装上，也只是不认农历节日，
        # 不能把公历节日（国庆/元旦）一起带崩
        monkeypatch.setattr(planner.holiday_calendar, "LunarDate", None)
        start, hint = planner.parse_start_date("国庆去广州", self.REF)
        assert (start.isoformat(), hint) == ("2026-10-01", "国庆")
        assert planner.parse_start_date("中秋去广州", self.REF) == (None, None)


class TestParseStartDate:
    REF: ClassVar[date] = date(2026, 9, 18)  # 周五

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("国庆节去广州玩", "2026-10-01"),  # 用户实际踩到的坑：之前排成了今天
            ("国庆去广州玩几天", "2026-10-01"),
            ("十一去广州看展", "2026-10-01"),
            ("周末想去广州玩两天", "2026-09-19"),  # 周五的最近周六
            ("下周末去广州", "2026-09-26"),
            ("下周五出发", "2026-09-25"),
            ("10月1号出发", "2026-10-01"),
            ("明天去广州", "2026-09-19"),
            ("后天去广州", "2026-09-20"),
            ("今天就想出发", "2026-09-18"),
            ("随便逛逛", None),  # 没说日期不该硬编一个
        ],
    )
    def test_解析出发日期(self, text, expected):
        got, _hint = planner.parse_start_date(text, self.REF)
        assert (got.isoformat() if got else None) == expected

    def test_命中原词一并返回供前端说明(self):
        # 用户写了"国庆"，就得能告诉他"已按国庆排"，而不是默默给个日期
        got, hint = planner.parse_start_date("国庆去广州玩几天", self.REF)
        assert got == date(2026, 10, 1)
        assert hint == "国庆"

    def test_十一月不会被误判成国庆(self):
        got, hint = planner.parse_start_date("十一月去广州玩三天", self.REF)
        assert (got, hint) == (None, None)

    def test_过了今年国庆就排明年(self):
        got, _ = planner.parse_start_date("国庆去广州玩", date(2026, 11, 5))
        assert got == date(2027, 10, 1)


class TestWeatherHint:
    def test_完全没有预报时说明未做天气规避(self):
        hint = planner.weather_hint(["2026-10-01"], {})
        # 空着会被当成功能坏了；必须说清"没做雨天规避"而不是"晴天"
        assert hint is not None
        assert "未做雨天规避" in hint

    def test_只有部分日期有预报时点名缺的日期(self):
        hint = planner.weather_hint(["2026-09-19", "2026-10-01"], {"2026-09-19": {}})
        assert hint is not None
        assert "2026-10-01" in hint

    def test_预报齐全时不提示(self):
        assert planner.weather_hint(["2026-09-19"], {"2026-09-19": {}}) is None
        assert planner.weather_hint([], {}) is None


class TestNeedsIndoor:
    @pytest.mark.parametrize(
        ("desc", "precip", "temp_max", "expected"),
        [
            ("雷阵雨", 0.5, 28.0, True),  # 强对流：安全风险，不只是体验差
            ("晴", 12.0, 30.0, True),  # 降水量达标
            ("晴", 0.0, 36.0, True),  # 高温
            ("多云", 1.0, 30.0, False),
            ("小雨", 2.0, 28.0, False),  # 小雨不构成不适合户外
            (None, None, None, False),
        ],
    )
    def test_坏天气判定(self, desc, precip, temp_max, expected):
        assert planner.needs_indoor(desc, precip, temp_max) is expected


class TestIsOutdoor:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("广东省博物馆", False),
            ("天河城购物中心", False),
            ("白云山", True),
            ("珠江夜游", True),
            ("广州塔", True),
            ("某个没听过的名字", True),  # 不确定时按户外处理（保守）
        ],
    )
    def test_室内外判定(self, text, expected):
        assert planner.is_outdoor(text) is expected


class TestAuditPlan:
    WEATHER_BAD: ClassVar[dict] = {"2026-09-19": {"desc": "雷阵雨", "needs_indoor": True}}
    WEATHER_GOOD: ClassVar[dict] = {"2026-09-19": {"desc": "晴", "needs_indoor": False}}

    def test_坏天气把户外项换成室内候选(self):
        plan = _plan([("2026-09-19", [("09:30", "白云山", "徒步")])])

        fixed, fixes = planner.audit_plan(plan, self.WEATHER_BAD, ["广东省博物馆"])

        assert fixed.plan[0].items[0].title == "广东省博物馆"
        assert fixed.plan[0].items[0].weather_adjusted is True
        assert fixes  # 调整说明要返回给用户看
        assert "白云山" in fixes[0]

    def test_审计后坏天气日不再出现户外安排(self):
        """本日最关键的断言：不依赖模型是否听话。"""
        plan = _plan([("2026-09-19", [("09:30", "白云山", "徒步"), ("20:00", "珠江夜游", "夜游")])])

        fixed, _ = planner.audit_plan(plan, self.WEATHER_BAD, ["广东省博物馆", "天河城购物中心"])

        for item in fixed.plan[0].items:
            assert not planner.is_outdoor(item.title, item.activity), item.title

    def test_室内候选不足时保留原内容但明确标注(self):
        plan = _plan([("2026-09-19", [("09:30", "白云山", "徒步")])])

        fixed, fixes = planner.audit_plan(plan, self.WEATHER_BAD, [])

        item = fixed.plan[0].items[0]
        assert item.title == "白云山"  # 没有替代品就不硬改内容
        assert item.weather_adjusted is True
        assert "建议改为室内" in fixes[0]
        assert "雷阵雨" in fixed.plan[0].weather_note

    def test_好天气不动任何安排(self):
        plan = _plan([("2026-09-19", [("09:30", "白云山", "徒步")])])

        fixed, fixes = planner.audit_plan(plan, self.WEATHER_GOOD, ["广东省博物馆"])

        assert fixed.plan[0].items[0].title == "白云山"
        assert fixed.plan[0].items[0].weather_adjusted is False
        assert fixes == []

    def test_没有天气数据时不改安排(self):
        plan = _plan([("2026-09-19", [("09:30", "白云山", "徒步")])])

        fixed, fixes = planner.audit_plan(plan, {}, ["广东省博物馆"])

        assert fixed.plan[0].items[0].title == "白云山"
        assert fixes == []

    def test_只调整户外项室内项保持原样(self):
        plan = _plan(
            [("2026-09-19", [("09:30", "广东省博物馆", "看展"), ("14:00", "白云山", "徒步")])]
        )

        fixed, _ = planner.audit_plan(plan, self.WEATHER_BAD, ["天河城购物中心"])

        assert fixed.plan[0].items[0].title == "广东省博物馆"  # 室内项不动
        assert fixed.plan[0].items[1].title == "天河城购物中心"


class TestAttachCoordinates:
    """地点坐标只从候选 POI 反查，不让模型编。

    模型编出来的经纬度看着很像真的，但错得离谱；
    "点开地图发现位置不对"比"点了没反应"更伤信任，所以宁可留空。
    """

    COORDS: ClassVar[dict] = {
        "白云山": {"lng": 113.2987, "lat": 23.1860},
        "南沙天后宫南沙沙滩": {"lng": 113.6044, "lat": 22.7528},
    }

    def test_命中的条目补上坐标(self):
        plan = _plan([("2026-09-19", [("09:30", "白云山", "徒步")])])

        assert planner.attach_coordinates(plan, self.COORDS) == 1
        assert plan.plan[0].items[0].lng == 113.2987
        assert plan.plan[0].items[0].lat == 23.1860

    def test_命不中的条目留空(self):
        # 留空时前端退回"按地名搜索"，不能凭空给一个坐标
        plan = _plan([("2026-09-19", [("12:00", "附近用餐", "午餐")])])

        assert planner.attach_coordinates(plan, self.COORDS) == 0
        assert plan.plan[0].items[0].lng is None
        assert plan.plan[0].items[0].lat is None

    def test_模型改了后缀也能对上(self):
        # 模型常把候选名改写成「白云山风景区」这类变体，包含匹配要能兜住
        plan = _plan([("2026-09-19", [("09:30", "白云山风景区", "徒步")])])

        planner.attach_coordinates(plan, self.COORDS)

        assert plan.plan[0].items[0].lng == 113.2987

    def test_没有候选坐标时不报错(self):
        plan = _plan([("2026-09-19", [("09:30", "白云山", "徒步")])])

        assert planner.attach_coordinates(plan, {}) == 0


class TestPlanToItineraryItems:
    def test_字段映射到行程表(self):
        result = {
            "plan": {
                "plan": [
                    {
                        "date": "2026-09-19",
                        "items": [
                            {
                                "time": "09:30",
                                "title": "白云山",
                                "activity": "徒步",
                                "reason": "早上凉快",
                            }
                        ],
                    }
                ]
            }
        }

        assert planner.plan_to_itinerary_items(result) == [
            {
                "date": "2026-09-19",
                "title": "白云山",
                "start_time": "09:30",
                "location": "白云山",
                "activity": "徒步",
                "note": "早上凉快",
            }
        ]

    def test_缺少标题或日期的条目被跳过(self):
        result = {
            "plan": {
                "plan": [
                    {"date": "2026-09-19", "items": [{"time": "09:30", "title": ""}]},
                    {"date": None, "items": [{"time": "10:00", "title": "白云山"}]},
                ]
            }
        }

        assert planner.plan_to_itinerary_items(result) == []

    def test_空结果不报错(self):
        assert planner.plan_to_itinerary_items({}) == []


class TestRenderText:
    def test_渲染包含天气提醒与调整说明(self):
        result = {
            "request": {"city": "广州"},
            "weather": {"2026-09-19": {"desc": "雷阵雨", "needs_indoor": True}},
            "plan": {
                "city": "广州",
                "days": 1,
                "summary": "雨天多排室内",
                "plan": [
                    {
                        "date": "2026-09-19",
                        "weather_note": "当天雷阵雨，已把 1 项户外安排调整为室内",
                        "items": [
                            {
                                "time": "09:30",
                                "title": "广东省博物馆",
                                "activity": "室内游览",
                                "reason": "避雨",
                                "weather_adjusted": True,
                            }
                        ],
                    }
                ],
            },
            "adjustments": ["2026-09-19：白云山（户外）→ 广东省博物馆（室内）"],
        }

        text = planner.render_text(result)

        assert "广州" in text
        assert "广东省博物馆" in text
        assert "已因天气调整" in text
        assert "不适合户外" in text
