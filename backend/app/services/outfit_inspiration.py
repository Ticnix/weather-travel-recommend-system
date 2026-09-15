"""穿搭灵感采集：为穿搭推荐补充社交平台上的真实搭配参考。

背景：穿搭建议原本只有规则引擎输出，内容偏「说明书」，缺少真实搭配参考。

数据来源与限制（实测结论）：
- **抖音**：搜索引擎索引良好，能拿到具体内容标题与链接 → 作为主要内容源
- **小红书**：对搜索引擎屏蔽严重，站内笔记基本搜不到（返回的都是社区首页）→
  改为生成「平台搜索直达链接」，用户点进去即可看到实时穿搭笔记
- 其他平台（微博 / B站 / 知乎等）命中即保留

上层通过 `fetch_outfit_ideas()` 获取，结果按参数缓存，避免频繁消耗搜索额度。
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from app.services.web_search_service import _search_tavily

logger = logging.getLogger(__name__)

# 平台识别：域名关键词 → 展示名
_PLATFORMS: tuple[tuple[str, str], ...] = (
    ("douyin.com", "抖音"),
    ("xiaohongshu.com", "小红书"),
    ("weibo.com", "微博"),
    ("bilibili.com", "B站"),
    ("zhihu.com", "知乎"),
    ("instagram.com", "Instagram"),
    ("youtube.com", "YouTube"),
)

# 通用 / 无效页面特征：这些不是具体穿搭内容，采集时丢弃
_JUNK_TITLE_MARKERS: tuple[str, ...] = (
    "你的生活兴趣社区",
    "Xiaohongshu",
    "RedNote",
    "Fashion - ",
    "抖音精选 - 首页",
    "首页 - ",
)


def _platform_of(url: str) -> str:
    for key, name in _PLATFORMS:
        if key in url:
            return name
    return "网页"


def _season_of(temp: float) -> str:
    """按气温推导季节性关键词，让搜索词更贴近当下。"""
    if temp >= 30:
        return "夏季"
    if temp >= 25:
        return "夏末初秋"
    if temp >= 18:
        return "秋季"
    if temp >= 10:
        return "深秋"
    return "冬季"


def build_portals(keyword: str) -> list[dict]:
    """生成各平台的「搜索直达」入口。

    小红书笔记搜不到，但它的搜索页可以直接打开，
    用户点进去就能看到实时穿搭内容，比给一个失效链接好。
    """
    kw = quote(keyword)
    return [
        {
            "platform": "小红书",
            "title": f"小红书搜「{keyword}」",
            "url": f"https://www.xiaohongshu.com/search_result?keyword={kw}",
        },
        {
            "platform": "抖音",
            "title": f"抖音搜「{keyword}」",
            "url": f"https://www.douyin.com/search/{kw}",
        },
        {
            "platform": "微博",
            "title": f"微博搜「{keyword}」",
            "url": f"https://s.weibo.com/weibo?q={kw}",
        },
        {
            "platform": "B站",
            "title": f"B站搜「{keyword}」",
            "url": f"https://search.bilibili.com/all?keyword={kw}",
        },
    ]


async def fetch_outfit_ideas(
    city: str = "广州",
    scene: str | None = None,
    preference: str | None = None,
    temp: float = 25.0,
    weather_desc: str = "",
) -> dict:
    """采集穿搭灵感。

    返回：
    {
        "keyword": "广州 秋季逛街穿搭",   # 实际使用的搜索词
        "season": "秋季",
        "posts": [{"title", "url", "platform", "snippet"}, …],
        "portals": [{"platform", "title", "url"}, …],
        "engine": "Tavily" | "none",
    }
    """
    from app.core.config import settings

    season = _season_of(temp)
    scene_kw = (scene or "").strip()
    # 拼出贴合当下天气 + 场景的搜索词，例如「广州 夏末初秋逛街穿搭」
    keyword = f"{city} {season}{scene_kw}穿搭"

    portals = build_portals(keyword)
    empty = {
        "keyword": keyword,
        "season": season,
        "posts": [],
        "portals": portals,
        "engine": "none",
    }

    if not settings.TAVILY_API_KEY:
        return empty

    queries = [
        f"site:douyin.com {season}{scene_kw}穿搭",
        f"{city} {int(temp)}度 {scene_kw}穿搭 抖音",
        f"小红书 {season} 穿搭 分享 笔记",
    ]

    batches = await asyncio.gather(*(_search_tavily(q, 6) for q in queries), return_exceptions=True)

    posts: list[dict] = []
    seen_urls: set[str] = set()
    for batch in batches:
        if isinstance(batch, BaseException):
            logger.info("穿搭灵感搜索失败: %s", batch)
            continue
        for r in batch:
            url = (r.get("url") or "").strip()
            title = (r.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue
            # 过滤社区首页之类的无效页
            if any(m in title for m in _JUNK_TITLE_MARKERS):
                continue
            if len(title) < 6:  # 标题过短基本不是内容页
                continue
            # 穿搭时效性强，丢弃明显过时的旧内容
            if any(f"{y}年" in title for y in range(2018, 2025)):
                continue
            seen_urls.add(url)
            posts.append(
                {
                    "title": title[:120],
                    "url": url,
                    "platform": _platform_of(url),
                    "snippet": (r.get("content") or "").strip()[:160],
                    "score": r.get("score", 0),
                }
            )

    # 按平台优先级 + 相关度排序：抖音内容质量最好，优先展示
    priority = {"抖音": 0, "小红书": 1, "B站": 2, "微博": 3, "知乎": 4}
    posts.sort(key=lambda p: (priority.get(p["platform"], 9), -float(p.get("score") or 0)))

    return {
        "keyword": keyword,
        "season": season,
        "posts": posts[:8],
        "portals": portals,
        "engine": "Tavily",
    }
