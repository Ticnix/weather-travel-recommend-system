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
from app.services import outfit_skill, rag_service, travel_skill, web_search_service
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


async def search_knowledge(query: str, top_k: int = 5) -> str:
    """从知识库（RAG）语义检索相关内容。

    知识库覆盖：广州气候、美食、交通、景点、住宿、穿搭、天气出行规划等。
    适合回答"广州哪里好玩""下雨天穿什么""广州美食推荐"等需要背景知识的问题。

    参数 query 是用户问题的自然语言描述，如"广州塔怎么去"。
    """
    if not query or not query.strip():
        return "检索问题不能为空，请描述你想了解的内容。"

    try:
        items = await rag_service.search(query.strip(), top_k=max(1, min(10, int(top_k))))
    except Exception as exc:  # noqa: BLE001 检索失败降级
        return f"知识库检索失败：{exc}"

    if not items:
        return "未找到相关知识。可尝试换一种说法，或询问天气、出行、穿搭类问题。"

    lines = [f"知识库检索到 {len(items)} 条相关内容："]
    for it in items:
        content = (it.get("content") or "")[:200].replace("\n", " ")
        lines.append(
            f"- [{it.get('title', '')}]（相似度 {it.get('similarity', 0):.2f}）{content}..."
        )
    return "\n".join(lines)


async def web_search(query: str, max_results: int = 5) -> str:
    """联网搜索实时信息（Tavily 优先，DuckDuckGo 兜底）。

    用于回答知识库和天气 API 都覆盖不到的实时问题，如"广州塔今天开放吗"、
    "最近广州有什么活动""某景区最新门票价格"等。
    """
    return await web_search_service.search(query, max_results)


async def plan_travel_route(origin: str, destination: str, city: str = "广州") -> str:
    """出行规划：从出发地到目的地，返回多套出行方案，融合时间/费用/天气三维评分并带天气提示。

    适用"从广州南站到广州塔怎么走""去白云山坐地铁还是打车"等。
    """
    return await travel_skill.plan_travel(origin, destination, city)


async def recommend_outfit(city: str = "广州", scene: str = "", preference: str = "") -> str:
    """穿搭推荐：结合天气（温度/降水/风）+ 活动场景 + 用户偏好，生成贴合场景的穿搭建议。

    适用"明天爬山穿什么""下雨天逛街穿什么""我怕冷，明天怎么穿"等。

    参数 scene 可选：爬山/逛街/夜游/商务/通勤/露营/骑行/观景/亲子/摄影；
    参数 preference 可选：怕冷/怕热/正式/运动/休闲/简约/时尚。
    """
    return await outfit_skill.recommend_outfit(city, scene or None, preference or None)