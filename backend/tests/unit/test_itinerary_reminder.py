"""行程提醒 Skill 单元测试：自然语言日期解析。

这是"AI 能听懂「后天」「大后天」"的底层支撑，
纯函数实现，是单元测试的理想对象。
"""

from datetime import date, timedelta

import pytest

from skills.itinerary_reminder.scripts import reminder


class TestParseDateExpression:
    def test_今天(self):
        assert reminder.parse_date_expression("今天有什么安排") == date.today().isoformat()
        assert reminder.parse_date_expression("今日天气") == date.today().isoformat()

    def test_明天(self):
        expect = (date.today() + timedelta(days=1)).isoformat()
        assert reminder.parse_date_expression("明天爬山穿什么") == expect

    def test_后天(self):
        expect = (date.today() + timedelta(days=2)).isoformat()
        assert reminder.parse_date_expression("后天去广州塔") == expect

    def test_大后天优先于后天(self):
        """「大后天」包含「后天」子串，解析顺序必须正确。"""
        expect = (date.today() + timedelta(days=3)).isoformat()
        assert reminder.parse_date_expression("大后天") == expect

    def test_标准日期格式(self):
        assert reminder.parse_date_expression("2026-09-20 去广州塔") == "2026-09-20"
        assert reminder.parse_date_expression("2026/09/20") == "2026-09-20"

    def test_中文年月日格式(self):
        assert reminder.parse_date_expression("2026年9月20日出行") == "2026-09-20"

    def test_月日格式自动补年份(self):
        result = reminder.parse_date_expression("9月20日有什么安排")
        assert result is not None
        assert result.endswith("-09-20")

    def test_无法解析返回None(self):
        assert reminder.parse_date_expression("随便说点什么吧") is None

    @pytest.mark.parametrize(
        "text",
        ["明天", "后天", "大后天", "2026-12-01", "12月1日"],
    )
    def test_各种表达都能解析出合法日期(self, text):
        result = reminder.parse_date_expression(text)
        assert result is not None
        # 必须是合法且格式统一的 ISO 日期
        date.fromisoformat(result)


class TestResolveCity:
    def test_从地点解析城市(self):
        assert reminder._resolve_city("上海迪士尼") == "上海"

    def test_空值返回None(self):
        assert reminder._resolve_city(None) is None

    def test_未知地点返回None(self):
        assert reminder._resolve_city("火星基地") is None


class TestConstants:
    def test_默认城市为广州(self):
        assert reminder.DEFAULT_CITY == "广州"
