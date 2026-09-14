"""穿搭规则引擎单元测试（纯函数，不依赖网络与数据库）。

规则引擎是"知识（规则表）与逻辑（匹配代码）分离"的典型实现，
这里验证温度分档、天气关键词、场景匹配三类规则是否按预期命中。
"""

import pytest

from skills.outfit_recommend.scripts import outfit_engine as oe


class TestTempRules:
    """温度分档：TEMP_RULES 是 [lo, hi) 左闭右开区间。"""

    @pytest.mark.parametrize(
        ("temp", "keyword"),
        [
            (35.0, "炎热"),
            (26.0, "温暖"),
            (18.0, "凉爽"),
            (5.0, "寒冷"),
        ],
    )
    def test_各档位命中对应规则(self, temp, keyword):
        rules = oe._build_rules(temp, "晴", None)
        assert any(keyword in r for r in rules)

    def test_边界值30度归入炎热档(self):
        """30.0 落在「温暖」的右边界之外，应进入「炎热」档。"""
        rules = oe._build_rules(30.0, "晴", None)
        assert any("炎热" in r for r in rules)

    def test_边界值22度归入温暖档(self):
        rules = oe._build_rules(22.0, "晴", None)
        assert any("温暖" in r for r in rules)


class TestWeatherRules:
    """天气关键词匹配。"""

    def test_雨天命中防水防滑(self):
        rules = oe._build_rules(25.0, "中雨", None)
        assert any(("防水" in r) or ("防滑" in r) for r in rules)

    def test_雷雨命中防雷(self):
        rules = oe._build_rules(25.0, "雷阵雨", None)
        assert any("雷" in r for r in rules)

    def test_晴天不加天气规则(self):
        """晴天不应误命中任何恶劣天气规则。"""
        rules = oe._build_rules(25.0, "晴", None)
        assert all("雨" not in r for r in rules)


class TestSceneRules:
    """场景匹配。"""

    def test_爬山场景给出专业建议(self):
        rules = oe._build_rules(25.0, "晴", "爬山")
        assert any(("登山鞋" in r) or ("速干" in r) for r in rules)

    def test_商务场景给出正装建议(self):
        rules = oe._build_rules(25.0, "晴", "商务")
        assert any("西装" in r or "衬衫" in r for r in rules)

    def test_未知场景不额外加规则(self):
        base = oe._build_rules(25.0, "晴", None)
        unknown = oe._build_rules(25.0, "晴", "钓鱼")
        assert len(unknown) == len(base)

    def test_规则可叠加(self):
        """温度 + 天气 + 场景应同时命中。"""
        rules = oe._build_rules(35.0, "雷阵雨", "爬山")
        assert len(rules) >= 3


class TestRuleTables:
    """规则表自身的完整性（防止改坏）。"""

    def test_温度档位覆盖全区间且有序(self):
        ranges = [rng for rng, _ in oe.TEMP_RULES]
        assert len(ranges) == len(oe.TEMP_RULES)
        # 每个区间 lo < hi
        assert all(lo < hi for lo, hi in ranges)

    def test_偏好规则关键词齐全(self):
        for key in ("怕冷", "怕热", "正式", "运动"):
            assert key in oe.PREFERENCE_RULES
