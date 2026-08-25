"""穿搭推荐 Skill：融合气象参数 + 场景 + 用户偏好，生成穿搭建议。

设计思路（规则引擎 + LLM 生成）：
1. 规则引擎：根据温度区间、天气类型、活动场景，检索匹配的穿搭规则（确定性）
2. 偏好调整：根据用户偏好（怕冷/怕热/正式/运动等）微调建议
3. 交给 LLM 生成最终的自然语言建议（结合知识库检索的上下文）

温度分档（℃）：
- 炎热 ≥30   ：轻薄透气
- 温暖 22~30 ：薄长袖 + 薄外套
- 凉爽 15~22 ：卫衣/毛衣 + 夹克
- 寒冷 <15   ：厚外套/羽绒服

天气类型：晴/多云/阴/雨/雪/雷/风/雾/霾
场景类型：爬山/逛街/夜游/商务/通勤/露营/骑行/观景/亲子/摄影
"""

from __future__ import annotations

from typing import Any

from app.services import rag_service
from app.services.weather_service import fetch_weather

# 温度档位 → 基础穿搭规则
TEMP_RULES: list[tuple[tuple[float, float], str]] = [
    ((30.0, 99.0), "炎热：轻薄透气的棉麻/速干面料，短袖短裤，注意防晒（遮阳帽+防晒霜）"),
    ((22.0, 30.0), "温暖：薄长袖/T恤 + 轻薄外套或开衫，早晚可叠穿"),
    ((15.0, 22.0), "凉爽：卫衣/针织衫 + 夹克或风衣，注意早晚温差叠穿"),
    ((-99.0, 15.0), "寒冷：厚外套/羽绒服 + 毛衣内搭，注意保暖（围巾手套）"),
]

# 天气类型 → 额外建议
WEATHER_RULES: dict[str, str] = {
    "雨": "雨天：防滑防水鞋 + 轻便防水外套，携带雨具，避免棉质易湿裤装",
    "雪": "雪天：保暖防滑靴 + 羽绒服，注意头部手部保暖",
    "雷": "雷雨：防水装备 + 避免金属物品，户外活动注意防雷",
    "风": "大风：防风外套，避免过于宽松衣物，户外避开风口",
    "雾": "雾天：穿亮色/反光衣物提高可见度，注意交通安全",
    "霾": "霾天：佩戴口罩，减少户外暴露，穿深色耐脏衣物",
}

# 场景类型 → 功能性建议
SCENE_RULES: dict[str, str] = {
    "爬山": "爬山：防滑运动鞋/登山鞋 + 速干透气衣物，备防晒和轻便雨衣，护膝可选",
    "逛街": "逛街：舒适平底鞋/运动鞋 + 轻便衣物，背包方便购物",
    "夜游": "夜游：备一件薄外套（夜间降温），亮色或反光元素提高安全性",
    "商务": "商务：正式衬衫/西装，深色为主，注意平整挺括",
    "通勤": "通勤：舒适鞋 + 易打理衣物，可叠穿应对室内外温差",
    "露营": "露营：速干衣 + 冲锋衣，备保暖层和防潮垫，夜间需加厚",
    "骑行": "骑行：紧身速干衣 + 防风外套，头盔手套，反光装备",
    "观景": "观景：防风外套 + 舒适鞋，高处风大注意保暖",
    "亲子": "亲子：轻便耐脏衣物 + 舒适鞋，备儿童替换衣物",
    "摄影": "摄影：深色耐脏衣物 + 舒适鞋，方便蹲起，备防雨罩",
}

# 用户偏好 → 调整方向
PREFERENCE_RULES: dict[str, str] = {
    "怕冷": "在基础建议上再加一件保暖层（如加绒内搭/厚外套）",
    "怕热": "优先轻薄透气面料，减少层数，选择浅色衣物",
    "正式": "以商务正装为主，兼顾天气保暖/凉爽",
    "运动": "以运动装为主，速干面料，运动鞋，方便活动",
    "休闲": "以休闲舒适为主，宽松剪裁",
    "简约": "少而精，基础款叠穿，颜色低调",
    "时尚": "可增加配饰、层次感搭配，颜色可大胆",
}


async def _get_weather_context(city: str | None) -> str:
    """拉取当前/预报天气，转成穿搭决策所需的气象参数文本。"""
    bundle = await fetch_weather(city or "广州")
    c = bundle.current
    daily = bundle.daily[0] if bundle.daily else None

    temp = daily.temp_max if daily else (c.temperature if c.temperature is not None else 25)
    weather_desc = (daily.weather_desc if daily else c.weather_desc) or "多云"
    precip = (daily.precipitation_sum if daily else c.precipitation) or 0
    wind = c.wind_scale if getattr(c, "wind_scale", None) else None

    ctx = f"气温最高 {temp}°C，天气 {weather_desc}，降水 {precip}mm"
    if wind:
        ctx += f"，风力 {wind}"
    return ctx


def _build_rules(temp: float, weather_desc: str, scene: str | None) -> list[str]:
    """根据温度/天气/场景，匹配穿搭规则，返回规则列表。"""
    rules: list[str] = []

    # 温度档
    for (lo, hi), rule in TEMP_RULES:
        if lo <= temp < hi:
            rules.append(rule)
            break

    # 天气
    for keyword, rule in WEATHER_RULES.items():
        if keyword in weather_desc:
            rules.append(rule)
            break

    # 场景
    if scene:
        for keyword, rule in SCENE_RULES.items():
            if keyword in scene:
                rules.append(rule)
                break

    return rules


async def recommend_outfit(
    city: str | None = None,
    scene: str | None = None,
    preference: str | None = None,
) -> str:
    """穿搭推荐主入口。

    参数：
    - city: 城市（默认广州）
    - scene: 活动场景（爬山/逛街/夜游等，可选）
    - preference: 用户偏好（怕冷/怕热/正式/运动等，可选）
    """
    # 1. 气象参数
    weather_ctx = await _get_weather_context(city)

    # 2. 温度值（用于规则匹配）
    bundle = await fetch_weather(city or "广州")
    daily = bundle.daily[0] if bundle.daily else None
    temp = (daily.temp_max if daily else (bundle.current.temperature or 25)) or 25
    weather_desc = (daily.weather_desc if daily else bundle.current.weather_desc) or "多云"

    # 3. 匹配规则
    rules = _build_rules(temp, weather_desc, scene)

    # 4. 用户偏好调整
    pref_rule = ""
    if preference:
        for keyword, rule in PREFERENCE_RULES.items():
            if keyword in preference:
                pref_rule = rule
                break

    # 5. RAG 检索穿搭知识（增强上下文）
    query = f"{weather_desc} {scene or ''} 穿搭"
    knowledge = ""
    try:
        hits = await rag_service.search(query, top_k=2)
        if hits:
            knowledge = "\n".join(f"- {h['content'][:150]}" for h in hits)
    except Exception:  # noqa: BLE001
        knowledge = ""

    # 6. 拼装结构化结果，交给 LLM 生成（在 MCP 工具层由 Agent 完成）
    lines = [
        f"【气象参数】{weather_ctx}",
        "【穿搭规则】",
    ]
    lines += [f"- {r}" for r in rules]
    if pref_rule:
        lines.append(f"- 用户偏好调整：{pref_rule}")
    if knowledge:
        lines.append("【知识库参考】")
        lines.append(knowledge)
    lines.append("\n请基于以上信息，用简洁友好的中文生成具体的穿搭建议（上衣/下装/鞋/配饰，可分点），并说明理由。")

    return "\n".join(lines)