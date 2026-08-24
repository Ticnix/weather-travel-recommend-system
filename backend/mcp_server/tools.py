"""MCP 工具实现（业务逻辑层）。

与 MCP 协议解耦：这里只写纯业务函数，由 server.py 用 @mcp.tool() 装饰注册。
好处：工具逻辑可单测、可被非 MCP 场景复用，也便于以后增删工具。

工具清单（Day 9）：
- get_weather     : 实时天气（城市名）
- get_forecast    : 未来 N 天预报（城市名 + 天数）
- search_news     : 资讯检索（关键词 + 类别）
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.news import News
from app.services.city_dict import all_supported_cities, lookup_city
from app.services.weather_service import fetch_weather, weather_to_text

# 支持的城市列表（供工具描述/参数提示使用）
_SUPPORTED_CITIES = "、".join(all_supported_cities())


async def get_weather(city: str) -> str:
    """查询指定城市实时天气。

    参数 city 支持中文名、拼音、常见别名（如"广州"/"gz"/"广州塔"）。
    """
    if not city or not city.strip():
        city = "广州"
    # 校验城市是否可解析（未知城市给出友好提示）
    if not lookup_city(city):
        return f"抱歉，暂不支持查询「{city}」的天气。当前支持：{_SUPPORTED_CITIES}。"

    bundle = await fetch_weather(city)
    return weather_to_text(bundle)


async def get_forecast(city: str, days: int = 3) -> str:
    """查询指定城市未来 N 天天气预报（1~7 天）。

    参数 days 越界时自动夹取到 1~7。
    """
    days = max(1, min(7, int(days)))
    if not city or not city.strip():
        city = "广州"
    if not lookup_city(city):
        return f"抱歉，暂不支持查询「{city}」的天气。当前支持：{_SUPPORTED_CITIES}。"

    bundle = await fetch_weather(city)
    # 截取前 days 天
    lines = [f"{city} 未来 {days} 天预报："]
    for d in bundle.daily[:days]:
        line = f"- {d.date}：{d.weather_desc or '未知'}，{d.temp_min}~{d.temp_max}°C"
        if d.precipitation_sum:
            line += f"，降水 {d.precipitation_sum}mm"
        lines.append(line)
    if bundle.alerts:
        lines.append("预警：")
        for a in bundle.alerts:
            lines.append(f"- [{a.level}] {a.title}：{a.detail}")
    return "\n".join(lines)


async def search_news(keyword: str, category: str | None = None, limit: int = 5) -> str:
    """从资讯库检索相关资讯。

    参数 category 可选：notice（公告）/ travel（出行）/ outfit（穿搭）/ news（通用）。
    """
    limit = max(1, min(10, int(limit)))
    async with AsyncSessionLocal() as db:
        stmt = (
            select(News)
            .where(News.is_published.is_(True))
            .order_by(News.is_top.desc(), News.id.desc())
            .limit(limit)
        )
        if category and category != "news":
            stmt = select(News).where(
                News.is_published.is_(True), News.category == category
            ).order_by(News.is_top.desc(), News.id.desc()).limit(limit)
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            stmt = select(News).where(
                News.is_published.is_(True), News.title.ilike(kw) | News.content.ilike(kw)
            ).order_by(News.is_top.desc(), News.id.desc()).limit(limit)

        rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return "未找到相关资讯。可尝试更换关键词，或查询公告/出行/穿搭类资讯。"

    lines = [f"检索到 {len(rows)} 条资讯："]
    for n in rows:
        # 截取前 120 字作为摘要
        summary = (n.content or "")[:120].replace("\n", " ")
        lines.append(f"- [{n.category}] {n.title}：{summary}...")
    return "\n".join(lines)