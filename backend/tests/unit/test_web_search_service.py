"""联网搜索服务测试（Tavily 优先 + DuckDuckGo 兜底）。

这里有两条关键路径必须保护：
1. **Tavily 失败自动降级到 DDG** —— 保证"没有 Key / 服务抖动"时 AI 仍能联网
2. **结果格式化成 LLM 可读文本** —— 上游（MCP 工具）依赖这个格式
"""

import json

import httpx
import pytest

from app.services import web_search_service as ws

TAVILY_URL = "https://api.tavily.com/search"
DDG_URL = "https://api.duckduckgo.com/"


class TestTavily:
    async def test_解析搜索结果(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        respx_mock.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "广州天气",
                            "url": "https://example.com/a",
                            "content": "今天多云",
                            "score": 0.87,
                        }
                    ]
                },
            )
        )
        results = await ws._search_tavily("广州天气", 5)
        assert len(results) == 1
        assert results[0]["title"] == "广州天气"
        assert results[0]["score"] == 0.87

    async def test_摘要被截断到300字(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        respx_mock.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"title": "t", "url": "u", "content": "长" * 1000}]},
            )
        )
        results = await ws._search_tavily("q", 5)
        assert len(results[0]["content"]) <= 300

    async def test_空结果返回空列表(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        respx_mock.post(TAVILY_URL).mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        assert await ws._search_tavily("q", 5) == []


class TestDuckDuckGo:
    async def test_解析摘要与相关主题(self, respx_mock):
        respx_mock.get(DDG_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "Heading": "广州",
                    "AbstractText": "广州是广东省省会",
                    "AbstractURL": "https://example.com/gz",
                    "RelatedTopics": [
                        {"Text": "白云山位于广州市区北部", "FirstURL": "https://example.com/bys"}
                    ],
                },
            )
        )
        results = await ws._search_ddg("广州", 5)
        assert len(results) == 2
        assert results[0]["url"] == "https://example.com/gz"

    async def test_无结果返回空列表(self, respx_mock):
        respx_mock.get(DDG_URL).mock(
            return_value=httpx.Response(200, json={"RelatedTopics": []})
        )
        assert await ws._search_ddg("q", 5) == []


class TestSearchEntry:
    """对外统一入口：Tavily 优先，失败降级 DDG。"""

    async def test_空关键词返回提示(self):
        assert "不能为空" in await ws.search("   ")

    async def test_优先使用Tavily(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        respx_mock.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"title": "标题A", "url": "https://a.com", "content": "摘要A"}]},
            )
        )
        text = await ws.search("广州天气")
        assert "Tavily" in text
        assert "标题A" in text
        assert "https://a.com" in text

    async def test_Tavily失败时降级到DDG(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        monkeypatch.setattr(ws.settings, "WEB_SEARCH_FALLBACK_DDG", True)
        respx_mock.post(TAVILY_URL).mock(side_effect=httpx.ConnectError("boom"))
        respx_mock.get(DDG_URL).mock(
            return_value=httpx.Response(
                200,
                json={"Heading": "兜底结果", "AbstractText": "来自 DDG", "AbstractURL": "https://ddg.com"},
            )
        )
        text = await ws.search("广州天气")
        assert "DuckDuckGo" in text
        assert "兜底结果" in text

    async def test_无Key时直接走DDG(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "")
        monkeypatch.setattr(ws.settings, "WEB_SEARCH_FALLBACK_DDG", True)
        respx_mock.get(DDG_URL).mock(
            return_value=httpx.Response(
                200,
                json={"Heading": "DDG", "AbstractText": "内容", "AbstractURL": "https://d.com"},
            )
        )
        text = await ws.search("测试")
        assert "DuckDuckGo" in text

    async def test_全部失败时给出友好提示(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        monkeypatch.setattr(ws.settings, "WEB_SEARCH_FALLBACK_DDG", True)
        respx_mock.post(TAVILY_URL).mock(side_effect=httpx.ConnectError("boom"))
        respx_mock.get(DDG_URL).mock(side_effect=httpx.ConnectError("boom"))

        text = await ws.search("测试")
        assert "未获取到结果" in text

    async def test_关闭DDG兜底且Tavily失败时返回提示(self, monkeypatch, respx_mock):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        monkeypatch.setattr(ws.settings, "WEB_SEARCH_FALLBACK_DDG", False)
        respx_mock.post(TAVILY_URL).mock(side_effect=httpx.ConnectError("boom"))

        text = await ws.search("测试")
        assert "未获取到结果" in text

    @pytest.mark.parametrize("n", [0, -5, 100])
    async def test_结果条数被限制在合法范围(self, monkeypatch, respx_mock, n):
        monkeypatch.setattr(ws.settings, "TAVILY_API_KEY", "fake-key")
        route = respx_mock.post(TAVILY_URL).mock(
            return_value=httpx.Response(
                200, json={"results": [{"title": "t", "url": "u", "content": "c"}]}
            )
        )
        await ws.search("测试", max_results=n)

        # 实际发给 Tavily 的 max_results 应被夹到 1~10（防止上游被刷爆或空结果）
        sent = json.loads(route.calls[0].request.content)
        assert 1 <= sent["max_results"] <= 10
