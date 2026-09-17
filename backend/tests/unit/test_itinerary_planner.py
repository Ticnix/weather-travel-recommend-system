"""AI 一键排行程测试（Day 40）。

**为什么这些用例能脱离 LLM 跑**：排程本身依赖模型（不稳定、测不了），
但「需求解析」与「天气审计」被刻意抽成了纯函数——
而这两块恰好是唯一可能出错、也唯一必须保证的地方。

最关键的断言只有一句：**审计之后，坏天气的日期里不允许再出现户外安排**。
这就是检查清单里「行程与真实天气不冲突」的真正含义。
"""

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
            ("排个十天行程", 5),  # 超上限按上限截断
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
