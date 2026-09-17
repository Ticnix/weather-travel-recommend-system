"""时序分析测试（Day 42）。

分两类：
- **纯函数**：区间计算、差值语义、口径对齐——这些是分析的"算法"，
  错了会得出看起来合理的假结论，必须逐条钉死
- **数据库**：验证聚合视图的时区日切与汇总口径
  （测试库用的是**同名普通视图**，聚合定义与线上连续聚合是同一份 SQL）
"""

from datetime import UTC, date, datetime

import pytest

from app.models.weather import WeatherHistory
from app.services import weather_analysis as wa


class TestPeriodMath:
    def test_月份区间是左闭右开(self):
        assert wa.month_period(2026, 9) == (date(2026, 9, 1), date(2026, 10, 1))

    def test_十二月跨到次年一月(self):
        # 12 月的下界要跨年，否则会算成 2026-13-01 直接报错
        assert wa.month_period(2026, 12) == (date(2026, 12, 1), date(2027, 1, 1))

    def test_按月平移跨年(self):
        assert wa.shift_month(2026, 1, -1) == (2025, 12)
        assert wa.shift_month(2026, 12, 1) == (2027, 1)

    def test_平移多个月(self):
        assert wa.shift_month(2026, 3, -5) == (2025, 10)


class TestDelta:
    def test_正常差值保留一位(self):
        assert wa.delta(29.14, 30.35) == -1.2

    @pytest.mark.parametrize("cur,prev", [(None, 30.0), (29.0, None), (None, None)])
    def test_任一侧缺失返回None而不是当成0(self, cur, prev):
        """最关键的一条：把缺失当 0 会算出"降水比去年少 100%"这种假结论。"""
        assert wa.delta(cur, prev) is None


class TestDeltaText:
    def test_上升带正号(self):
        assert wa.delta_text(1.2, "°C") == "+1.2°C"

    def test_下降带负号且只出现一次(self):
        # 曾经容易写成 "-" + value 导致 "--1.2"
        assert wa.delta_text(-1.2, "°C") == "-1.2°C"

    def test_极小差值算持平(self):
        assert wa.delta_text(0.01, "°C") == "持平"

    def test_无数据(self):
        assert wa.delta_text(None, "°C") == "无数据"


class TestVerdict:
    def test_同时有气温与降水(self):
        assert wa.build_verdict(1.2, -30.5, "同比") == "同比：气温 +1.2°C，降水 -30.5mm"

    def test_只有气温时不提降水(self):
        assert wa.build_verdict(1.2, None, "环比") == "环比：气温 +1.2°C"

    def test_都没有时说明原因(self):
        assert "无可用数据" in wa.build_verdict(None, None, "同比")


class TestAlignPreviousEnd:
    """口径对齐：本期进行中时，同期只取相同天数。"""

    def test_截到相同天数(self):
        # 2025-09 起点 + 17 天 → 2025-09-18（半开上界）
        assert wa.align_previous_end(date(2025, 9, 1), date(2025, 10, 1), 17) == date(2025, 9, 18)

    def test_短月按实际天数钳制(self):
        """2 月只有 28 天：本期按 30 天对齐时不能越界到 3 月。"""
        assert wa.align_previous_end(date(2025, 2, 1), date(2025, 3, 1), 30) == date(2025, 3, 1)

    def test_天数超过区间时不超过原上界(self):
        assert wa.align_previous_end(date(2025, 4, 1), date(2025, 5, 1), 99) == date(2025, 5, 1)


class TestSummarizeRows:
    def _row(self, **kw):
        from types import SimpleNamespace

        base = {
            "temp_avg": 28.0,
            "temp_max": 33.0,
            "temp_min": 23.0,
            "precip_sum": 1.0,
            "humidity_avg": 60.0,
            "samples": 1,
        }
        return SimpleNamespace(**{**base, **kw})

    def test_常规汇总(self):
        rows = [self._row(), self._row(temp_avg=30.0, temp_max=35.0, temp_min=25.0, precip_sum=3.0)]
        out = wa.summarize_rows(rows)
        assert out["days"] == 2
        assert out["temp_avg"] == 29.0
        assert out["temp_max"] == 35.0
        assert out["temp_min"] == 23.0
        assert out["precip_total"] == 4.0

    def test_缺温度的日期不参与均值但仍计入天数(self):
        rows = [self._row(), self._row(temp_avg=None, humidity_avg=None)]
        out = wa.summarize_rows(rows)
        assert out["days"] == 2
        assert out["temp_avg"] == 28.0  # 只有一条参与均值
        assert out["humidity_avg"] == 60.0

    def test_空输入不报错(self):
        out = wa.summarize_rows([])
        assert out["days"] == 0
        assert out["temp_avg"] is None
        assert out["precip_total"] is None


def _day_row(
    loc: str, day: str, temp_max: float, temp_min: float, precip: float = 0.0
) -> WeatherHistory:
    """造一条日统计行（与 _daily_row 的字段约定一致：temperature=最高、feels_like=最低）。"""
    return WeatherHistory(
        time=datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC),
        location_code=loc,
        temperature=temp_max,
        feels_like=temp_min,
        precipitation=precip,
        humidity=None,
        is_forecast=False,
        raw={"daily": {"sunrise": None, "sunset": None}},
    )


class TestAggregateTimezone:
    async def test_日切按北京时区而不是UTC(self, db):
        """00:00 UTC = 北京 08:00，仍属同一天。

        如果聚合按 UTC 切，9/14 08:00（北京）会被算成 9/14，
        而 9/14 00:30（北京，= 9/13 16:30 UTC）会被算成 9/13——
        日期整体错位。用本地日期输出才能对上。
        """
        db.add(_day_row("tz_test", "2026-09-14", 33.0, 24.0))
        await db.commit()

        series = await wa.daily_series(db, "tz_test", days=30, end=date(2026, 9, 20))
        assert [item["date"] for item in series] == ["2026-09-14"]

    async def test_只统计指定城市(self, db):
        db.add(_day_row("loc_a", "2026-09-14", 30.0, 20.0))
        db.add(_day_row("loc_b", "2026-09-14", 35.0, 25.0))
        await db.commit()

        series = await wa.daily_series(db, "loc_a", days=30, end=date(2026, 9, 20))
        assert len(series) == 1
        assert series[0]["temp_max"] == 30.0


class TestPeriodSummaryDb:
    async def test_极值取区间内的最高与最低(self, db):
        db.add_all(
            [
                _day_row("sum_c", "2026-09-01", 30.0, 22.0, 1.0),
                _day_row("sum_c", "2026-09-02", 35.0, 20.0, 2.0),
            ]
        )
        await db.commit()

        out = await wa.period_summary(db, "sum_c", date(2026, 9, 1), date(2026, 10, 1))
        assert out["days"] == 2
        assert out["temp_max"] == 35.0
        assert out["temp_min"] == 20.0
        assert out["precip_total"] == 3.0
        # 日均按 (最高+最低)/2 口径：两天分别是 26.0 与 27.5，均值 26.75 → 26.8
        assert out["temp_avg"] == 26.8

    async def test_区间外数据不计入(self, db):
        db.add_all(
            [
                _day_row("sum_d", "2026-08-31", 40.0, 30.0),
                _day_row("sum_d", "2026-09-05", 30.0, 20.0),
            ]
        )
        await db.commit()

        out = await wa.period_summary(db, "sum_d", date(2026, 9, 1), date(2026, 10, 1))
        assert out["days"] == 1
        assert out["temp_max"] == 30.0


class TestCompareMonth:
    async def test_无同期数据时如实说明而不是拿0算(self, db):
        db.add(_day_row("cmp_a", "2026-09-10", 30.0, 22.0))
        await db.commit()

        out = await wa.compare_month(db, "cmp_a", kind="yoy", year=2026, month=9)

        assert out["available"] is False
        assert "2025-09" in out["reason"]
        assert out["diff"]["temp_avg"] is None  # 不是 -30 之类的假数值
        assert "verdict" not in out

    async def test_完全无数据时说明两侧都缺(self, db):
        out = await wa.compare_month(db, "cmp_none", kind="yoy", year=2020, month=3)
        assert out["available"] is False
        assert "2020-03" in out["reason"] and "2019-03" in out["reason"]

    async def test_同比差值正确(self, db):
        db.add_all(
            [
                _day_row("cmp_b", "2026-09-02", 33.0, 25.0, 5.0),
                _day_row("cmp_b", "2026-09-03", 33.0, 25.0, 5.0),
                _day_row("cmp_b", "2025-09-02", 30.0, 22.0, 1.0),
                _day_row("cmp_b", "2025-09-03", 30.0, 22.0, 1.0),
            ]
        )
        await db.commit()

        out = await wa.compare_month(db, "cmp_b", kind="yoy", year=2026, month=9)

        # 2026-09 是未来月份（今天 2026-09-17），不触发"进行中"对齐
        assert out["available"] is True
        assert out["current"]["days"] == 2
        assert out["previous"]["days"] == 2
        assert out["diff"]["temp_avg"] == 3.0
        assert out["diff"]["precip_total"] == 8.0
        assert "气温 +3.0°C" in out["verdict"]

    async def test_进行中的月份会对齐同期天数(self, db, monkeypatch):
        """今天在 9 月 10 日时，同期只取到 9 月 10 日，避免"17 天 vs 30 天"。"""
        import app.services.weather_analysis as mod

        class _FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 9, 10)

        monkeypatch.setattr(mod, "date", _FakeDate)

        rows = [_day_row("cmp_c", f"2026-09-{d:02d}", 30.0, 22.0) for d in range(1, 11)]
        rows += [_day_row("cmp_c", f"2025-09-{d:02d}", 30.0, 22.0) for d in range(1, 21)]
        db.add_all(rows)
        await db.commit()

        out = await mod.compare_month(db, "cmp_c", kind="yoy", year=2026, month=9)

        assert out["aligned"] is True
        assert out["aligned_days"] == 10
        assert out["previous"]["days"] == 10  # 不是 20
        assert "口径可比" in out["sample_note"]

    async def test_环比对比上个月(self, db):
        db.add_all(
            [
                _day_row("cmp_d", "2026-08-05", 34.0, 26.0),
                _day_row("cmp_d", "2026-07-05", 30.0, 24.0),
            ]
        )
        await db.commit()

        out = await wa.compare_month(db, "cmp_d", kind="mom", year=2026, month=8)
        assert out["kind_label"] == "环比"
        assert out["previous_period"] == "2026-07"
        assert out["available"] is True
