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


async def fetch_weather_news(limit: int = 15) -> list[dict]:
    """抓取中国天气网资讯频道的新闻列表。

    返回：[{title, url}, ...]，url 统一为 https 绝对地址（详情页要内嵌展示）。
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

        url = href if href.startswith("http") else WEATHER_NEWS_BASE + href
        url = url.replace("http://", "https://")  # 统一 https，避免 iframe 混合内容
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": title, "url": url})
        if len(results) >= limit:
            break

    return results


async def collect_news_articles(db: AsyncSession, limit: int = 15) -> dict:
    """采集中国天气网气象新闻并写入 news 表（按标题去重）。"""
    articles = await fetch_weather_news(limit=limit)
    created = 0

    for a in articles:
        exists = await db.scalar(select(News.id).where(News.title == a["title"]))
        if exists:
            continue

        db.add(
            News(
                title=a["title"][:200],
                content=(
                    f"【来源】中国天气网\n"
                    f"【标题】{a['title']}\n\n"
                    f"本条为气象资讯，完整内容请查看下方内嵌的原文页面。\n"
                    f"原文链接：{a['url']}"
                ),
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


async def collect_alerts(
    db: AsyncSession,
    area_keyword: str = "广东",
    max_pages: int = 5,
) -> dict:
    """采集中央气象台预警并写入 news 表（按标题去重）。"""
    alerts = await fetch_alerts(area_keyword, max_pages=max_pages)
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
    return {"fetched": len(alerts), "created": created}


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
    area_keyword: str = "广东",
    with_forecast: bool = True,
    with_news: bool = True,
    max_pages: int = 5,
    news_limit: int = 15,
) -> dict:
    """采集全部气象资讯：气象预警（中央气象台）+ 气象新闻（中国天气网）+ 本地天气简报。"""
    alert_stat = await collect_alerts(db, area_keyword=area_keyword, max_pages=max_pages)

    news_stat: dict = {"created": 0}
    if with_news:
        news_stat = await collect_news_articles(db, limit=news_limit)

    forecast_stat: dict = {"created": 0}
    if with_forecast:
        forecast_stat = await collect_forecast_digest(db)

    total = (
        alert_stat.get("created", 0)
        + news_stat.get("created", 0)
        + forecast_stat.get("created", 0)
    )
    return {
        "area": area_keyword,
        "alerts": alert_stat,
        "news": news_stat,
        "forecast": forecast_stat,
        "created_total": total,
    }
