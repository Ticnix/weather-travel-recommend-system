"""联网搜索服务：Tavily 优先 + DuckDuckGo 兜底。

设计：
- Tavily：AI 场景专用搜索引擎，返回结构化、干净的结果（标题/URL/摘要/相关性评分）。
  需配置 TAVILY_API_KEY（免费注册 https://tavily.com）。
- DuckDuckGo：无 Key 即可用的兜底方案，Tavily 未配置或调用失败时自动降级。

对外暴露统一的 search(query) 接口，上层（MCP 工具）不感知具体用了哪个引擎。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Tavily 搜索 API
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def _search_tavily(query: str, max_results: int) -> list[dict[str, Any]]:
    """调用 Tavily 搜索 API。返回 [{title, url, content, score}, ...]。"""
    payload = {
        "api_key": settings.TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": (item.get("content") or "")[:300],
                "score": round(float(item.get("score", 0)), 4),
            }
        )
    return results


async def _search_ddg(query: str, max_results: int) -> list[dict[str, Any]]:
    """调用 DuckDuckGo Instant Answer API 兜底（无需 Key）。

    注意：这是 DDG 的公开 Instant Answer 接口，返回字段较简单，
    拿不到完整网页摘要时，退化为返回相关主题链接。
    """
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://api.duckduckgo.com/", params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict[str, Any]] = []
    # AbstractText（摘要）优先
    if data.get("AbstractText"):
        results.append(
            {
                "title": data.get("Heading") or query,
                "url": data.get("AbstractURL", ""),
                "content": data["AbstractText"][:300],
                "score": 1.0,
            }
        )
    # 相关主题（RelatedTopics）
    for topic in data.get("RelatedTopics", [])[: max_results - len(results)]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append(
                {
                    "title": (topic.get("Text") or "")[:60],
                    "url": topic.get("FirstURL", ""),
                    "content": topic.get("Text", "")[:300],
                    "score": 0.5,
                }
            )
    return results


async def search(query: str, max_results: int = 5) -> str:
    """联网搜索，返回格式化文本供 LLM 阅读。

    优先 Tavily，未配置 Key 或失败时降级 DuckDuckGo。
    """
    if not query or not query.strip():
        return "搜索关键词不能为空。"

    max_results = max(1, min(10, int(max_results)))
    query = query.strip()

    results: list[dict[str, Any]] = []
    engine = ""

    # 优先 Tavily
    if settings.TAVILY_API_KEY:
        try:
            results = await _search_tavily(query, max_results)
            engine = "Tavily"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tavily 搜索失败，降级 DuckDuckGo: %s", exc)

    # 兜底 DuckDuckGo
    if not results and settings.WEB_SEARCH_FALLBACK_DDG:
        try:
            results = await _search_ddg(query, max_results)
            engine = "DuckDuckGo"
        except Exception as exc:  # noqa: BLE001
            logger.warning("DuckDuckGo 搜索也失败: %s", exc)

    if not results:
        return "联网搜索未获取到结果，可能是网络问题或搜索服务暂不可用。"

    lines = [f"联网搜索（{engine}）结果如下："]
    for r in results:
        lines.append(f"- {r['title']}\n  来源：{r['url']}\n  摘要：{r['content']}")
    return "\n".join(lines)