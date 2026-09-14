"""穿搭推荐 Skill 核心逻辑（scripts）。

规则引擎（温度/天气/场景/偏好）+ RAG 增强。
规则说明见 references/ 下各文档，此处为可执行匹配逻辑。
"""

from __future__ import annotations

from typing import Any

from app.services import rag_service
from app.services.weather_service import fetch_weather

TEMP_RULES: list[tuple[tuple[float, float], str]] = [
    ((30.0, 99.0), "炎热：轻薄透气的棉麻/速干面料，短袖短裤，注意防晒（遮阳帽+防晒霜）"),
    ((22.0, 30.0), "温暖：薄长袖/T恤 + 轻薄外套或开衫，早晚可叠穿"),
    ((15.0, 22.0), "凉爽：卫衣/针织衫 + 夹克或风衣，注意早晚温差叠穿"),
    ((-99.0, 15.0), "寒冷：厚外套/羽绒服 + 毛衣内搭，注意保暖（围巾手套）"),
]

# 注意顺序：更"危险"的天气现象放前面，便于阅读时优先看到关键提醒
# （命中规则时不再 break，因此「雷阵雨」会同时拿到防雷与防雨两条建议）
WEATHER_RULES: dict[str, str] = {
    "雷": "雷雨：防水装备 + 避免金属物品，户外活动注意防雷",
    "雪": "雪天：保暖防滑靴 + 羽绒服，注意头部手部保暖",
    "雨": "雨天：防滑防水鞋 + 轻便防水外套，携带雨具，避免棉质易湿裤装",
    "风": "大风：防风外套，避免过于宽松衣物，户外避开风口",
    "雾": "雾天：穿亮色/反光衣物提高可见度，注意交通安全",
    "霾": "霾天：佩戴口罩，减少户外暴露，穿深色耐脏衣物",
}

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

PREFERENCE_RULES: dict[str, str] = {
    "怕冷": "在基础建议上再加一件保暖层（如加绒内搭/厚外套）",
    "怕热": "优先轻薄透气面料，减少层数，选择浅色衣物",
    "正式": "以商务正装为主，兼顾天气保暖/凉爽",
    "运动": "以运动装为主，速干面料，运动鞋，方便活动",
    "休闲": "以休闲舒适为主，宽松剪裁",
    "简约": "少而精，基础款叠穿，颜色低调",
    "时尚": "可增加配饰、层次感搭配，颜色可大胆",
}


def _build_rules(temp: float, weather_desc: str, scene: str | None) -> list[str]:
    rules: list[str] = []
    for (lo, hi), rule in TEMP_RULES:
        if lo <= temp < hi:
            rules.append(rule)
            break
    # 不 break：天气现象可能同时命中多条
    # （如「雷阵雨」既需要防雷、也需要防雨），只取第一条会漏掉关键提醒
    for keyword, rule in WEATHER_RULES.items():
        if keyword in weather_desc:
            rules.append(rule)
    if scene:
        for keyword, rule in SCENE_RULES.items():
            if keyword in scene:
                rules.append(rule)
                break
    return rules


async def run(city: str | None = None, scene: str | None = None, preference: str | None = None) -> str:
    """穿搭推荐主入口，返回结构化文本（交给 LLM 生成最终建议）。"""
    data = await outfit_structured(city, scene, preference)
    weather = data["weather"]
    weather_ctx = f"气温最高 {weather['temp']}°C，天气 {weather['desc']}，降水 {weather['precip']}mm"
    lines = [f"【气象参数】{weather_ctx}", "【穿搭规则】"]
    lines += [f"- {r}" for r in data["rules"]]
    if data["preference_rule"]:
        lines.append(f"- 用户偏好调整：{data['preference_rule']}")
    if data["knowledge"]:
        lines.append("【知识库参考】")
        lines.append(data["knowledge"])
    lines.append("\n请基于以上信息，用简洁友好的中文生成具体的穿搭建议（上衣/下装/鞋/配饰，可分点），并说明理由。")
    return "\n".join(lines)


async def outfit_structured(
    city: str | None = None,
    scene: str | None = None,
    preference: str | None = None,
) -> dict[str, Any]:
    """穿搭推荐结构化入口，返回可直接用于前端渲染的 dict。

    结构：
    {
      "city": "…",
      "weather": {"desc", "temp", "precip", "min", "max"},
      "scene": …, "preference": …,
      "temp_rule": str | null,      # 温度档基础建议
      "rules": [str, …],            # 命中规则（温度/天气/场景/偏好）
      "preference_rule": str | null,
      "knowledge": str,             # RAG 参考文本
      "suggestion": str             # 基于规则的整合文案
    }
    """
    bundle = await fetch_weather(city or "广州")
    daily = bundle.daily[0] if bundle.daily else None
    temp = (daily.temp_max if daily else (bundle.current.temperature or 25)) or 25
    weather_desc = (daily.weather_desc if daily else bundle.current.weather_desc) or "多云"
    precip = (daily.precipitation_sum if daily else bundle.current.precipitation) or 0

    rules = _build_rules(temp, weather_desc, scene)
    temp_rule = next(
        (rule for (lo, hi), rule in TEMP_RULES if lo <= temp < hi), None
    )

    pref_rule = ""
    if preference:
        for keyword, rule in PREFERENCE_RULES.items():
            if keyword in preference:
                pref_rule = rule
                break

    # RAG 检索穿搭知识
    knowledge = ""
    try:
        hits = await rag_service.search(f"{weather_desc} {scene or ''} 穿搭", top_k=2)
        if hits:
            knowledge = "\n".join(f"- {h['content'][:150]}" for h in hits)
    except Exception:  # noqa: BLE001
        knowledge = ""

    # 基于规则整合一段可直接展示的文案
    parts = list(rules)
    if pref_rule:
        parts.append(pref_rule)
    suggestion = "今日建议：" + "；".join(parts) if parts else "暂无明确的穿搭建议。"

    return {
        "city": city or "广州",
        "weather": {
            "desc": weather_desc,
            "temp": temp,
            "precip": precip,
        },
        "scene": scene,
        "preference": preference,
        "temp_rule": temp_rule,
        "rules": rules,
        "preference_rule": pref_rule or None,
        "knowledge": knowledge,
        "suggestion": suggestion,
    }