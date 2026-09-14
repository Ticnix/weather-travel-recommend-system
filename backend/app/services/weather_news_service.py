"""气象资讯采集服务：从权威公开数据源抓取真实气象资讯。

数据源（均免费、无需 API Key）：
1. 中央气象台预警接口（www.nmc.cn/rest/findAlarm）
   —— 全国气象预警实时数据，按地区关键词筛选（默认广东）
2. 本系统已有的天气数据（和风天气 / Open-Meteo）
   —— 生成目标城市的「未来天气简报」资讯

采集结果写入 news 表，前端「气象资讯」直接展示；
按标题去重，重复采集不会产生重复数据。
"""

from __future__ import annotations

import logging
from datetime import date
from html.parser import HTMLParser

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News
from app.services.article_extractor import fetch_article_texts

logger = logging.getLogger(__name__)

# 中国天气网资讯（气象新闻）—— 详情页同样支持 https 内嵌
WEATHER_NEWS_URL = "https://news.weather.com.cn/"
WEATHER_NEWS_BASE = "https://news.weather.com.cn"

NMC_ALARM_URL = "http://www.nmc.cn/rest/findAlarm"
# 原文链接统一用 https：详情页会以 iframe 内嵌展示原文，
# 若用 http 会与站点的 https 冲突，被浏览器按“混合内容”拦截
NMC_BASE = "https://www.nmc.cn"

# 中央气象台会校验 UA，缺省会返回异常内容
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# 资讯分类
CATEGORY_ALERT = "alert"  # 气象预警
CATEGORY_FORECAST = "news"  # 天气预报简报（归入普通资讯）

# 广州本地关键词：用于过滤资讯，保证「气象资讯」板块内容与广州相关
LOCAL_KEYWORDS: tuple[str, ...] = (
    "广州", "广东", "华南", "粤", "珠江", "珠三角", "花城", "羊城",
)

# Tavily 本地资讯搜索词（每条消耗 1 次搜索额度）；偏向「新闻」而非通用天气页
TAVILY_LOCAL_QUERIES: tuple[str, ...] = (
    "广州 天气 预警 新闻",
    "广州 暴雨 台风 最新",
    "广州 气象 通报",
)

# 通用天气导航页特征词：这类页面只有预报入口、没有资讯内容，采集时丢弃
GENERIC_TITLE_MARKERS: tuple[str, ...] = (
    "天气预报", "天气查询", "15天", "7天天气", "气象台,tqyb", "城市预报",
    "信息公开", "门户网站", "网站首页",
)


def _is_local(*texts: str | None) -> bool:
    """判断给定文本是否与广州本地相关。"""
    joined = " ".join(t for t in texts if t)
    return any(k in joined for k in LOCAL_KEYWORDS)


async def fetch_alerts(
    area_keyword: str = "广东",
    max_pages: int = 5,
    page_size: int = 20,
) -> list[dict]:
    """抓取中央气象台预警，返回标题含 area_keyword 的记录。

    返回：[{alert_id, title, issuetime, url, pic}, ...]
    """
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
        for page in range(1, max_pages + 1):
            try:
                resp = await client.get(
                    NMC_ALARM_URL, params={"pageNo": page, "pageSize": page_size}
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("抓取中央气象台预警失败（第 %s 页）: %s", page, exc)
                break

            rows = ((payload.get("data") or {}).get("page") or {}).get("list") or []
            if not rows:
                break

            for item in rows:
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                if area_keyword and area_keyword not in title:
                    continue
                results.append(
                    {
                        "alert_id": item.get("alertid", ""),
                        "title": title,
                        "issuetime": item.get("issuetime", ""),
                        "url": NMC_BASE + (item.get("url") or ""),
                        "pic": item.get("pic") or "",
                    }
                )
    return results


class _LinkParser(HTMLParser):
    """提取页面中的 <a> 文本与 href。"""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: str = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._text = ""

    def handle_data(self, data):
        if self._href is not None:
            self._text += data.strip()

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, self._text))
            self._href = None


async def fetch_weather_news(limit: int = 15, local_only: bool = True) -> list[dict]:
    """抓取中国天气网资讯频道的新闻列表。

    - local_only=True：只保留与广州/广东相关的条目（资讯板块本地化要求）
    - 返回：[{title, url}, ...]，url 统一为 https 绝对地址（详情页要内嵌展示）
    """
    async with httpx.AsyncClient(
        timeout=15.0, headers=_HEADERS, follow_redirects=True
    ) as client:
        try:
            resp = await client.get(WEATHER_NEWS_URL)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("抓取中国天气网资讯失败: %s", exc)
            return []

    resp.encoding = "utf-8"
    parser = _LinkParser()
    parser.feed(resp.text)

    results: list[dict] = []
    seen: set[str] = set()
    for href, text in parser.links:
        # 站点会在标题前加「推荐」等前缀，这里清理掉
        title = text.strip().lstrip("推荐").strip()
        if not href or not (8 <= len(title) <= 80):
            continue
        # 排除视频/生活类栏目，只保留资讯正文页
        if "/video/" in href or "/life/" in href:
            continue
        if not (".shtml" in href or "/2026" in href or "/2025" in href):
            continue
        # 资讯板块要求本地化：过滤掉纯外地新闻
        if local_only and not _is_local(title):
            continue

        url = href if href.startswith("http") else WEATHER_NEWS_BASE + href
        url = url.replace("http://", "https://")  # 统一 https，避免 iframe 混合内容
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": title, "url": url})
        if len(results) >= limit:
            break

    return results


async def collect_news_articles(
    db: AsyncSession, limit: int = 15, local_only: bool = True
) -> dict:
    """采集中国天气网气象新闻并写入 news 表（按标题去重，默认只保留本地相关）。"""
    articles = await fetch_weather_news(limit=limit, local_only=local_only)
    # 并发抓取原文正文：抓到的直接入库渲染，抓不到的仍可点原文链接
    texts = await fetch_article_texts([a["url"] for a in articles]) if articles else {}
    created = 0

    for a in articles:
        exists = await db.scalar(select(News.id).where(News.title == a["title"]))
        if exists:
            continue

        full_text = texts.get(a["url"], "")
        db.add(
            News(
                title=a["title"][:200],
                content=(
                    f"【来源】中国天气网\n"
                    f"【标题】{a['title']}\n\n"
                    f"本条为气象资讯，完整内容请查看下方正文或原文链接。\n"
                    f"原文链接：{a['url']}"
                ),
                full_text=full_text or None,
                cover_url=None,
                source_url=a["url"],
                category=CATEGORY_FORECAST,  # 归入普通资讯
                author="中国天气网",
                is_published=True,
                is_top=False,
            )
        )
        created += 1

    await db.commit()
    return {"fetched": len(articles), "created": created}


async def collect_tavily_news(
    db: AsyncSession,
    queries: tuple[str, ...] = TAVILY_LOCAL_QUERIES,
    limit_per_query: int = 6,
) -> dict:
    """用 Tavily 联网搜索采集**广州本地**气象资讯（需配置 TAVILY_API_KEY）。

    - 依次执行多个本地搜索词并合并去重，再过滤掉与广州无关的条目
    - 抓取原文正文存入 `full_text`：详情页可直接阅读完整内容，
      不再依赖 iframe 内嵌（多数新闻站禁止内嵌，iframe 会显示空白）
    """
    # 局部导入：避免模块级循环依赖
    from app.core.config import settings
    from app.services.web_search_service import _search_tavily

    if not settings.TAVILY_API_KEY:
        return {"created": 0, "skipped": "未配置 TAVILY_API_KEY"}

    merged: list[dict] = []
    seen_urls: set[str] = set()
    for q in queries:
        try:
            part = await _search_tavily(q, limit_per_query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tavily 采集失败（%s）: %s", q, exc)
            continue
        for r in part:
            url = (r.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(r)

    # 先筛出候选，再并发抓取原文正文（抓不到则降级为仅摘要 + 原文链接）
    candidates: list[dict] = []
    for r in merged:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        if not (8 <= len(title) <= 200) or not url:
            continue
        # 丢弃纯导航页（如「XX天气预报查询」），只保留有实质内容的资讯
        if any(m in title for m in GENERIC_TITLE_MARKERS):
            continue
        summary = (r.get("content") or "").strip()
        # 本地化过滤：标题与摘要都不含本地关键词则丢弃
        if not _is_local(title, summary):
            continue
        candidates.append({"title": title, "url": url, "summary": summary})

    texts = await fetch_article_texts([c["url"] for c in candidates]) if candidates else {}

    created = 0
    for c in candidates:
        title, url, summary = c["title"], c["url"], c["summary"]
        if await db.scalar(select(News.id).where(News.title == title)):
            continue

        full_text = texts.get(url, "")
        db.add(
            News(
                title=title,
                content=(
                    f"【来源】联网搜索\n"
                    f"【摘要】{summary or '（无摘要）'}\n\n"
                    f"（原文正文见下方正文区；若为空则请点击原文链接查看）\n"
                    f"原文链接：{url}"
                ),
                full_text=full_text or None,
                cover_url=None,
                source_url=url,
                category=CATEGORY_FORECAST,
                author="联网搜索",
                is_published=True,
                is_top=False,
            )
        )
        created += 1

    await db.commit()
    return {"fetched": len(merged), "created": created}


async def collect_alerts(
    db: AsyncSession,
    area: str = "广州",
    max_pages: int = 5,
    fallback: str | None = None,
) -> dict:
    """采集中央气象台预警并写入 news 表（按标题去重）。

    默认**严格只取 area（广州）本地预警**，保证「气象资讯」板块全部与广州相关；
    若确实希望本地无预警时回退到更大范围（如「广东」），可显式传入 fallback。
    """
    alerts = await fetch_alerts(area, max_pages=max_pages)
    used_area = area
    if not alerts and fallback:
        alerts = await fetch_alerts(fallback, max_pages=max_pages)
        used_area = fallback
    created = 0

    for a in alerts:
        exists = await db.scalar(select(News.id).where(News.title == a["title"]))
        if exists:
            continue

        content = (
            f"【发布单位】中央气象台\n"
            f"【发布时间】{a['issuetime']}\n"
            f"【预警内容】{a['title']}\n\n"
            f"请相关地区公众注意防范，及时关注当地气象台发布的最新预警信息。\n"
            f"原文链接：{a['url']}"
        )
        db.add(
            News(
                title=a["title"][:200],
                content=content,
                cover_url=a["pic"] or None,
                source_url=a["url"] or None,
                category=CATEGORY_ALERT,
                author="中央气象台",
                is_published=True,
                is_top=False,
            )
        )
        created += 1

    await db.commit()
    return {"fetched": len(alerts), "created": created, "area": used_area}


async def collect_forecast_digest(db: AsyncSession, city: str = "广州") -> dict:
    """用本系统天气数据生成「未来天气简报」并写入 news 表。

    标题带日期，同一天重复采集不会重复写入。
    """
    # 局部导入：避免 services 之间的循环依赖
    from app.services.weather_service import fetch_weather

    try:
        bundle = await fetch_weather(city)
    except Exception as exc:  # noqa: BLE001
        logger.warning("生成天气简报失败：%s", exc)
        return {"created": 0, "error": str(exc)}

    today = date.today().isoformat()
    title = f"{city}未来天气简报（{today}）"
    exists = await db.scalar(select(News.id).where(News.title == title))
    if exists:
        return {"created": 0, "skipped": True}

    c = bundle.current
    lines = [
        f"【城市】{city}",
        f"【当前实况】{c.weather_desc or '未知'}，气温 {c.temperature}°C"
        + (f"，体感 {c.feels_like}°C" if c.feels_like is not None else "")
        + (f"，湿度 {c.humidity}%" if c.humidity is not None else ""),
        "",
        "【未来几天预报】",
    ]
    for d in bundle.daily[:7]:
        line = f"· {d.date}：{d.weather_desc or '未知'}，{d.temp_min}~{d.temp_max}°C"
        if d.precipitation_sum:
            line += f"，降水 {d.precipitation_sum}mm"
        lines.append(line)

    if bundle.alerts:
        lines.append("")
        lines.append("【预警提示】")
        for a in bundle.alerts:
            lines.append(f"· [{a.level}] {a.title}：{a.detail}")

    lines.append("")
    lines.append("数据来源：本系统气象数据服务（和风天气 / Open-Meteo）")

    db.add(
        News(
            title=title,
            content="\n".join(lines),
            cover_url=None,
            category=CATEGORY_FORECAST,
            author="气象数据服务",
            is_published=True,
            is_top=False,
        )
    )
    await db.commit()
    return {"created": 1, "title": title}


async def collect_all(
    db: AsyncSession,
    area: str = "广州",
    with_forecast: bool = True,
    with_news: bool = True,
    with_tavily: bool = True,
    max_pages: int = 5,
    news_limit: int = 15,
) -> dict:
    """采集全部气象资讯，「气象资讯」板块统一本地化为广州内容。数据源：

    - 气象预警：中央气象台（广州优先，无则广东全省）
    - 气象新闻：中国天气网（只保留广州/广东相关）
    - 本地资讯：Tavily 联网搜索 广州天气 / 暴雨 / 台风
    - 天气简报：本系统广州天气数据
    """
    alert_stat = await collect_alerts(db, area=area, max_pages=max_pages)

    news_stat: dict = {"created": 0}
    if with_news:
        news_stat = await collect_news_articles(db, limit=news_limit, local_only=True)

    tavily_stat: dict = {"created": 0}
    if with_tavily:
        tavily_stat = await collect_tavily_news(db)

    forecast_stat: dict = {"created": 0}
    if with_forecast:
        forecast_stat = await collect_forecast_digest(db)

    total = (
        alert_stat.get("created", 0)
        + news_stat.get("created", 0)
        + tavily_stat.get("created", 0)
        + forecast_stat.get("created", 0)
    )
    return {
        "area": area,
        "alerts": alert_stat,
        "news": news_stat,
        "tavily": tavily_stat,
        "forecast": forecast_stat,
        "created_total": total,
    }
