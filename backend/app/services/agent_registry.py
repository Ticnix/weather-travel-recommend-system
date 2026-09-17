"""领域 Agent 注册表（Day 41）。

多智能体协作的第一步不是画流程图，而是**把工具按领域分好组**。

单 Agent 的问题是「所有工具都交给同一个模型挑」：候选有 10 个，
描述全塞进提示词，模型每次都要在"该用哪个"上做一次判断——
歧义大（`search_my_plans` 与 `check_itinerary_weather` 就极易混），
token 也贵。拆成领域后每个 Agent 只带自己那 1~3 个工具：

| 好处 | 说明 |
| --- | --- |
| 选对工具的概率上升 | 候选从 10 个降到 1~3 个 |
| token 成本下降 | 工具描述不便宜，每域只带自己那份 |
| 提示词能写得更具体 | 天气 Agent 只管天气，不必兼顾穿搭与路线 |

⚠️ **工具名必须与 MCP server / local_tools 里注册的名字逐字一致**：
写错不会报任何错，只会让某个 Agent 手里没有工具、于是凭记忆瞎答。
所以这里配了一组「注册表 ↔ 真实工具」的一致性测试守着。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Domain:
    """一个领域 Agent 的定义。"""

    key: str
    label: str
    tools: tuple[str, ...]
    keywords: tuple[str, ...]
    prompt: str = field(default="")
    # 模板式表达的补充匹配（关键词枚举不完的那些）
    patterns: tuple[str, ...] = field(default=())

    def matches(self, text: str) -> bool:
        """文本是否指向该领域：关键词命中，或正则命中。

        为什么还要正则：有些说法是**模板**而不是固定词——
        "玩两天 / 玩三天 / 玩五天"用关键词要枚举到天荒地老，
        一条 `玩[0-9一二三四五六七八九十两]+天` 就覆盖了。
        （这个缺口是实测发现的：'周末想去广州玩两天' 原本路由不到行程领域。）
        """
        if any(keyword in text for keyword in self.keywords):
            return True
        return any(re.search(pattern, text) for pattern in self.patterns)


# ---------------------------------------------------------------------------
# 领域定义
#
# keywords 只放**高置信**的词：命中即路由，不再问 LLM。
# 弱词（如「推荐」「怎么样」）故意不放——它们会把闲聊误判成业务意图。
# ---------------------------------------------------------------------------
DOMAINS: dict[str, Domain] = {
    "weather": Domain(
        key="weather",
        label="天气",
        tools=("get_weather", "get_forecast"),
        keywords=(
            "天气",
            "气温",
            "多少度",
            "几度",
            "下雨",
            "降雨",
            "降水",
            "晴天",
            "阴天",
            "多云",
            "台风",
            "湿度",
            "风力",
            "预报",
            "冷吗",
            "热吗",
            "要不要带伞",
        ),
        prompt=(
            "你是天气查询助手。用 get_weather 查实时天气、get_forecast 查未来预报，"
            "只回答天气本身（温度、降水、风力、湿度），不要延伸到穿搭或路线——"
            "那些有专门的助手负责。数据必须来自工具，禁止编造。"
        ),
    ),
    "outfit": Domain(
        key="outfit",
        label="穿搭",
        tools=("recommend_outfit",),
        keywords=(
            "穿搭",
            "穿什么",
            "怎么穿",
            "该穿",
            "穿衣服",
            "着装",
            "穿多少",
            "穿鞋",
            "怕冷",
            "怕热",
        ),
        prompt=(
            "你是穿搭建议助手。用 recommend_outfit 获取建议"
            "（把用户提到的场景如爬山/逛街、偏好如怕冷，作为参数传入）。"
            "回答要具体到单品与厚度，不要泛泛而谈。"
        ),
    ),
    "route": Domain(
        key="route",
        label="路线",
        tools=("plan_travel_route",),
        keywords=(
            "路线",
            "怎么走",
            "怎么去",
            "怎么到达",
            "出行方案",
            "交通",
            "地铁",
            "公交",
            "驾车",
            "开车",
            "打车",
            "骑行",
            "多远",
            "多久能到",
        ),
        prompt=(
            "你是出行路线助手。用 plan_travel_route 查询从出发地到目的地的方案"
            "（含时间/费用/天气评分）。若用户没说出发地，先用默认出发地给方案，"
            "并顺便问一句实际出发地。"
        ),
    ),
    "itinerary": Domain(
        key="itinerary",
        label="行程",
        tools=("check_itinerary_weather", "plan_trip", "search_my_plans"),
        keywords=(
            "行程",
            "日程",
            "安排",
            "我的计划",
            "明天有什么",
            "后天有什么",
            "帮我排",
            "排个",
            "玩几天",
            "几日游",
            "我上传",
            "我的攻略",
            "我的笔记",
        ),
        prompt=(
            "你是行程助手，负责三件事：\n"
            "1. 用户问自己已有的行程安排、或行程当天要注意什么 → check_itinerary_weather\n"
            '2. 用户要新排一份行程（如"周末想去广州玩两天"）→ plan_trip\n'
            "3. 用户问自己上传的攻略/笔记内容 → search_my_plans\n"
            "注意 1 与 3 的区别：行程表是结构化的（日期/地点/活动），"
            "私有知识库是文档，别用错。"
        ),
        # 排行程的请求多是模板式表达（"周末想去广州玩两天"/"帮我排个三日游"），
        # 固定关键词覆盖不全，用正则兜住
        patterns=(
            r"玩[0-9一二三四五六七八九十两]+天",
            r"[0-9一二三四五六七八九十两]+日游",
            r"排[个一]?份?行程",
            r"规划.{0,4}行程",
        ),
    ),
    "knowledge": Domain(
        key="knowledge",
        label="攻略资讯",
        tools=("search_knowledge", "search_news", "web_search"),
        keywords=(
            "景点",
            "美食",
            "好吃",
            "好玩",
            "攻略",
            "酒店",
            "住宿",
            "特产",
            "历史",
            "文化",
            "哪里玩",
            "哪里吃",
            "资讯",
            "新闻",
            "公告",
            "报道",
            "开放时间",
            "门票",
        ),
        prompt=(
            "你是本地攻略与资讯助手：本地攻略用 search_knowledge，"
            "站内资讯用 search_news，实时性信息（景区是否开放、最新活动、票价）"
            "用 web_search。只讲检索到的内容，查不到就说查不到。"
        ),
    ),
}

# 领域路由的稳定顺序（结果按此排序，保证同一问题每次路由结果一致）
DOMAIN_ORDER: tuple[str, ...] = tuple(DOMAINS)

# 领域依赖：命中左边时，右边也要一起跑。
#
# 目前只有一条：**穿搭依赖天气**。用户问"明天爬山穿什么"时，
# 他想要的不只是"建议穿冲锋衣"，还有"明天 18℃ 有雨"这个前提——
# 少了它，穿搭建议就是悬空的。实测单 Agent 的提示词里也是这么要求的
# （要求同时调天气与穿搭），多 Agent 拆分后这条约束必须显式补回来，
# 否则会静默地比原来答得少。
#
# 反过来刻意**不加**：
# - route → weather：路线评分内部已经含天气，再加一次是重复调用
# - itinerary → weather：check_itinerary_weather 本身就会取当天天气
DOMAIN_DEPENDS: dict[str, tuple[str, ...]] = {
    "outfit": ("weather",),
}


def route_domains(text: str) -> list[str]:
    """按关键词把问题路由到一个或多个领域（纯函数，不调 LLM）。

    返回空列表表示「没有明确领域」——由调用方走通用回答
    （闲聊，或需要模型自己判断的问题）。

    设计说明：这里**刻意不做"命中多个就裁剪"**。
    用户问"明天去广州塔穿什么、怎么去"时，穿搭/路线都该答，
    少答一个就是漏答；再加上依赖补全（穿搭→天气），
    得到的就是与单 Agent 同等的覆盖范围。
    """
    hit = {key for key in DOMAIN_ORDER if DOMAINS[key].matches(text)}
    for key in list(hit):
        hit.update(DOMAIN_DEPENDS.get(key, ()))
    # 按注册顺序返回，保证同一问题的路由结果稳定（便于测试与对比）
    return [key for key in DOMAIN_ORDER if key in hit]


def tools_for_domain(key: str) -> tuple[str, ...]:
    """该领域的工具名（未知领域返回空元组）。"""
    domain = DOMAINS.get(key)
    return domain.tools if domain else ()


def group_tools(tools: list) -> dict[str, list]:
    """把工具对象按领域分组。

    未在任何领域出现的工具放进 `_unassigned`——**不静默丢弃**：
    将来加了工具却忘了登记，应该能从返回值里看出来（有测试守着）。
    """
    by_name = {getattr(tool, "name", ""): tool for tool in tools}
    grouped: dict[str, list] = {}
    assigned: set[str] = set()

    for key, domain in DOMAINS.items():
        picked = [by_name[name] for name in domain.tools if name in by_name]
        grouped[key] = picked
        assigned.update(tool.name for tool in picked)

    grouped["_unassigned"] = [tool for name, tool in by_name.items() if name not in assigned]
    return grouped
