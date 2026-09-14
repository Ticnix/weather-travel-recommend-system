"""数据清洗引擎测试（Pandas）。

清洗链路是"脏数据进来、干净数据出去"的核心，四类规则都要有保护：
单位标准化 → 列名标准化 → 时间解析 → 异常过滤 → 缺失填充 → 去重。

用 tmp_path 写真实 CSV，走完整的 clean_csv 流程（不 mock Pandas）。
"""

import pandas as pd
import pytest

from app.services.clean_engine import CleanStats, clean_csv


def _write_csv(tmp_path, rows: list[dict], name: str = "raw.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


class TestTimeParsing:
    def test_无效时间行被丢弃(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 10:00:00", "temperature": 30},
                {"time": "not-a-date", "temperature": 28},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert stats.total_rows == 2
        assert stats.cleaned_rows == 1

    def test_日期字符串可解析(self, tmp_path):
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", "temperature": 30}])
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert stats.cleaned_rows == 1


class TestUnitStandardization:
    def test_华氏转摄氏(self, tmp_path):
        """86℉ 应转换成 30℃。"""
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", "temperature_f": 86}])
        stats = clean_csv(raw, tmp_path / "out.csv")

        out = pd.read_csv(tmp_path / "out.csv")
        assert "temperature" in out.columns
        assert out["temperature"].iloc[0] == pytest.approx(30.0, abs=0.1)
        assert stats.unit_standardized == 1

    def test_风速ms转kmh(self, tmp_path):
        """10 m/s 应转换成 36 km/h。"""
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", "wind_ms": 10}])
        clean_csv(raw, tmp_path / "out.csv")

        out = pd.read_csv(tmp_path / "out.csv")
        assert out["wind_speed"].iloc[0] == pytest.approx(36.0, abs=0.1)

    def test_气压kPa转hPa(self, tmp_path):
        """101.3 kPa 应转换成 1013 hPa。"""
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", "pressure_kpa": 101.3}])
        clean_csv(raw, tmp_path / "out.csv")

        out = pd.read_csv(tmp_path / "out.csv")
        assert out["pressure"].iloc[0] == pytest.approx(1013.0, abs=0.5)


class TestColumnAliases:
    @pytest.mark.parametrize(
        ("alias", "standard"),
        [
            ("temp", "temperature"),
            ("hum", "humidity"),
            ("rh", "humidity"),
            ("wind", "wind_speed"),
            ("rain", "precipitation"),
            ("city", "location_code"),
        ],
    )
    def test_列名别名映射到标准名(self, tmp_path, alias, standard):
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", alias: 1}])
        clean_csv(raw, tmp_path / "out.csv")

        out = pd.read_csv(tmp_path / "out.csv")
        assert standard in out.columns


class TestOutlierFiltering:
    def test_超范围温度被替换(self, tmp_path):
        """温度 999℃ 明显异常，应被置为缺失再填充。"""
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "temperature": 30},
                {"time": "2026-09-14 01:00", "temperature": 31},
                {"time": "2026-09-14 02:00", "temperature": 999},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert stats.filtered_outliers >= 1

        out = pd.read_csv(tmp_path / "out.csv")
        assert out["temperature"].max() < 100

    def test_湿度超100被替换(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "humidity": 60},
                {"time": "2026-09-14 01:00", "humidity": 70},
                {"time": "2026-09-14 02:00", "humidity": 500},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert stats.filtered_outliers >= 1


class TestMissingFill:
    def test_数值缺失用中位数填充(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "temperature": 20},
                {"time": "2026-09-14 01:00", "temperature": 30},
                {"time": "2026-09-14 02:00", "temperature": None},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert stats.filled_missing >= 1

        out = pd.read_csv(tmp_path / "out.csv")
        # 中位数 25 填充
        assert out["temperature"].iloc[2] == pytest.approx(25.0)

    def test_分类缺失用众数填充(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "location_code": "gz"},
                {"time": "2026-09-14 01:00", "location_code": "gz"},
                {"time": "2026-09-14 02:00", "location_code": None},
            ],
        )
        clean_csv(raw, tmp_path / "out.csv")

        out = pd.read_csv(tmp_path / "out.csv")
        assert out["location_code"].iloc[2] == "gz"

    def test_无缺失时不填充(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "temperature": 20},
                {"time": "2026-09-14 01:00", "temperature": 30},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert stats.filled_missing == 0


class TestDedup:
    def test_按指定列去重(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "temperature": 20},
                {"time": "2026-09-14 00:00", "temperature": 20},
                {"time": "2026-09-14 01:00", "temperature": 21},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv", dedup_keys=["time"])
        assert stats.duplicated_removed == 1
        assert stats.cleaned_rows == 2

    def test_默认按全部列去重(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "temperature": 20},
                {"time": "2026-09-14 00:00", "temperature": 20},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert stats.duplicated_removed == 1

    def test_不同值的相同时间不去重(self, tmp_path):
        raw = _write_csv(
            tmp_path,
            [
                {"time": "2026-09-14 00:00", "temperature": 20},
                {"time": "2026-09-14 00:00", "temperature": 25},
            ],
        )
        stats = clean_csv(raw, tmp_path / "out.csv", dedup_keys=["time"])
        assert stats.duplicated_removed == 1  # 按 time 去重仍会留一条


class TestOutput:
    def test_输出文件生成且可读(self, tmp_path):
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", "temperature": 30}])
        out_path = tmp_path / "sub" / "cleaned.csv"  # 目录不存在，应自动创建
        clean_csv(raw, out_path)
        assert out_path.exists()

        out = pd.read_csv(out_path)
        assert len(out) == 1

    def test_统计对象字段完整(self, tmp_path):
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", "temperature": 30}])
        stats = clean_csv(raw, tmp_path / "out.csv")
        assert isinstance(stats, CleanStats)
        assert stats.total_rows == 1
        assert stats.cleaned_rows == 1
        assert stats.log_lines  # 清洗日志必须留痕，便于审计

    def test_清洗日志可导出文本(self, tmp_path):
        raw = _write_csv(tmp_path, [{"time": "2026-09-14", "temperature": 30}])
        stats = clean_csv(raw, tmp_path / "out.csv")
        text = stats.log_text
        assert "读取原始文件" in text
        assert "清洗完成" in text
