"""天气客户端解析逻辑测试。

外部天气 API 返回的都是"字符串温度、八方位风向、区间风力"这类原始数据，
这里验证把它们转成内部结构时的健壮性——
**数据源换了（和风 / Open-Meteo）解析层也不能崩**。
"""

import pytest

from app.services import qweather_client as qw
from app.services import weather_client as wc


class TestWindDirection:
    """风向角度 → 八方位中文。"""

    @pytest.mark.parametrize(
        ("deg", "expect"),
        [
            (0, "北"),
            (45, "东北"),
            (90, "东"),
            (135, "东南"),
            (180, "南"),
            (225, "西南"),
            (270, "西"),
            (315, "西北"),
        ],
    )
    def test_八方位换算(self, deg, expect):
        assert wc._wind_dir(deg) == expect

    def test_空值返回None(self):
        assert wc._wind_dir(None) is None

    def test_360度等同正北(self):
        assert wc._wind_dir(360) == "北"

    def test_边界角度就近取整(self):
        """22.4° 仍算北风，22.5° 起算东北风。"""
        assert wc._wind_dir(22.4) == "北"
        assert wc._wind_dir(23.0) == "东北"


class TestQWeatherConversions:
    """和风返回值的类型转换与容错。"""

    @pytest.mark.parametrize(
        ("raw", "expect"),
        [
            ("30", 30.0),
            ("-5.5", -5.5),
            ("0", 0.0),
        ],
    )
    def test_数值字符串转float(self, raw, expect):
        assert qw._to_float(raw) == expect

    @pytest.mark.parametrize("raw", [None, "", "--", "abc"])
    def test_异常输入返回None(self, raw):
        """和风在无数据时会返回 '--'，必须容错而不是抛异常。"""
        assert qw._to_float(raw) is None

    @pytest.mark.parametrize(
        ("raw", "expect"),
        [
            ("3", 3),
            ("3-4", 4),  # 区间取较大值，偏保守
            ("1-3", 3),
            ("5-6", 6),
        ],
    )
    def test_风力等级取区间较大值(self, raw, expect):
        assert qw._wind_beaufort(raw) == expect

    def test_风力格式异常返回负一(self):
        assert qw._wind_beaufort("unknown") == -1


class TestDateParsing:
    """时间字符串解析。"""

    def test_和风时间格式(self):
        dt = qw._parse_qweather_dt("2026-09-14T14:03+08:00")
        assert dt.year == 2026
        assert dt.month == 9
        assert dt.day == 14

    def test_空值返回当前时间而非报错(self):
        """解析失败必须兜底，不能让天气接口整体挂掉。"""
        dt = qw._parse_qweather_dt(None)
        assert dt is not None

    def test_异常格式兜底(self):
        dt = qw._parse_qweather_dt("not-a-date")
        assert dt is not None


class TestOpenMeteoHelpers:
    """Open-Meteo 客户端的数组取值辅助。"""

    def test_按下标取值(self):
        assert wc._idx([1, 2, 3], 1) == 2

    def test_越界返回None(self):
        assert wc._idx([1], 5) is None

    def test_空数组返回None(self):
        assert wc._idx(None, 0) is None
        assert wc._idx([], 0) is None
