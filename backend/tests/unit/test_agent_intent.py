"""AI 意图识别测试 —— Day 21 修复 BUG 的回归用例。

**背景**：`POST /api/v1/chat` 曾出现意图识别稳定返回 `other` 的问题
（直接调 `chat()` 却正常），根因是意图识别完全依赖 LLM 分类输出、
而该分类在 HTTP 场景不稳定。

**修复方案**：强关键词预判优先——高置信词直接定意图、跳过 LLM 分类。

这套用例的价值在于：**不依赖 LLM、不依赖网络**就能锁住修复效果，
以后任何人改动意图识别逻辑，跑一下就知道有没有破坏。
"""

import pytest

from app.services import agent


class TestStrongKeywordIntent:
    """强关键词预判：高置信直接定意图。"""

    @pytest.mark.parametrize(
        ("text", "expect"),
        [
            ("广州今天天气怎么样", "weather"),
            ("明天会下雨吗", "weather"),
            ("今天气温多少度", "weather"),
            ("有台风预警吗", "weather"),
            ("明天爬山穿什么", "outfit"),
            ("商务场合着装建议", "outfit"),
            ("从广州南站到广州塔怎么走", "travel"),
            ("去白云山坐地铁还是公交", "travel"),
            ("打车过去要多久能到", "travel"),
            ("广州有什么好吃的", "knowledge"),
            ("推荐几个广州景点", "knowledge"),
            ("广州有什么特产", "knowledge"),
        ],
    )
    def test_高置信问题直接命中意图(self, text, expect):
        assert agent._strong_keyword_intent(text) == expect

    @pytest.mark.parametrize("text", ["你好啊", "随便聊聊", "今天心情不错", "嗯嗯"])
    def test_闲聊不会误判(self, text):
        assert agent._strong_keyword_intent(text) is None

    def test_复合问句能命中意图(self):
        """「明天去广州塔玩，适合穿什么，怎么去最方便」同时含穿搭与出行。"""
        result = agent._strong_keyword_intent("明天去广州塔玩，适合穿什么，怎么去最方便")
        assert result is not None
        assert result in {"weather", "outfit", "travel", "knowledge"}

    def test_天气与穿搭交叠时按词表顺序命中(self):
        """「下雨天该怎么穿」同时含「下雨」（天气）与「怎么穿」（穿搭）。

        强词表的遍历顺序决定了结果——命中任意一个相关意图都是合理的，
        这里锁定"不会判给完全无关的意图（如 other）"。
        """
        result = agent._strong_keyword_intent("下雨天该怎么穿")
        assert result in {"weather", "outfit"}

    def test_空字符串不命中(self):
        assert agent._strong_keyword_intent("") is None


class TestWeakKeywordIntent:
    """弱关键词兜底：仅在 LLM 分类失败时使用。"""

    def test_命中天气关键词(self):
        assert agent._keyword_intent("今天天气如何") == "weather"

    def test_未命中返回other(self):
        assert agent._keyword_intent("嗯嗯好的") == "other"


class TestIntentTables:
    """意图词表自身的完整性（防止改坏）。"""

    def test_强关键词表非空(self):
        assert agent._STRONG_INTENT_KEYWORDS

    def test_强关键词只包含有效意图(self):
        assert set(agent._STRONG_INTENT_KEYWORDS) <= {"weather", "outfit", "travel", "knowledge"}

    def test_工具意图集合正确(self):
        assert agent.TOOL_INTENTS == {"weather", "travel", "outfit", "knowledge"}

    def test_每个意图都有强关键词(self):
        for intent in ("weather", "outfit", "travel", "knowledge"):
            assert agent._STRONG_INTENT_KEYWORDS.get(intent), f"{intent} 缺少强关键词"

    def test_资讯关键词已定义(self):
        assert "资讯" in agent._NEWS_KEYWORDS

    def test_强关键词覆盖弱关键词(self):
        """强词表应是弱词表的"高置信子集"，不应出现强词没有而弱词有的意图。"""
        assert set(agent._STRONG_INTENT_KEYWORDS) <= set(agent._INTENT_KEYWORDS) | {"outfit"}
