"""Agent 本地工具（进程内，用于有「用户态」的工具）。

为什么私有知识库检索走本地工具、不走 MCP：
- MCP 工具跑在独立子进程（stdio 传输），contextvars 用户上下文跨不了进程；
- 用户私有检索需要知道「当前是哪个用户」，天然依赖 Agent 进程内的上下文；
- 因此：无状态公共工具（天气/资讯/公共知识库/联网搜索）走 MCP，
  有用户态的私有检索走本地工具，两者在 Agent 层合并绑定。

这样既保留了 MCP 的可插拔价值，又正确支持多租户数据隔离。
"""

from __future__ import annotations

from langchain_core.tools import tool

from app.services import user_knowledge_service
from app.services.user_context import get_current_user_id
from skills.itinerary_planner.scripts import planner
from skills.itinerary_reminder.scripts import reminder


@tool
async def search_my_plans(query: str, top_k: int = 5) -> str:
    """在当前登录用户自己的私有知识库（上传的出行计划/旅游攻略/笔记）中检索。

    仅检索当前用户本人上传的内容，与其他用户隔离。
    适用"我的行程计划第二天去哪""我上次收藏的餐厅"等个性化问题。

    Args:
        query: 检索问题，如"我的行程第二天去哪里"。
        top_k: 返回条数，1~10，默认 5。
    """
    user_id = get_current_user_id()
    if user_id is None:
        return "当前未登录，无法检索个人知识库。请先登录后重试。"

    if not query or not query.strip():
        return "检索问题不能为空。"

    items = await user_knowledge_service.search(user_id, query.strip(), top_k)
    if not items:
        return "你的个人知识库中暂无相关内容。可先上传你的出行计划或旅游笔记。"

    lines = [f"你的个人知识库检索到 {len(items)} 条相关内容："]
    for it in items:
        content = (it.get("content") or "")[:200].replace("\n", " ")
        lines.append(
            f"- [{it.get('title', '')}]（相似度 {it.get('similarity', 0):.2f}）{content}..."
        )
    return "\n".join(lines)


@tool
async def check_itinerary_weather(query: str) -> str:
    """查询当前登录用户某天的行程安排，并结合当天天气给出出行提醒与推荐。

    适用场景：用户问"明天有什么安排""后天要注意什么""我的行程当天天气如何"等。
    会自动解析用户问题中的日期（今天/明天/后天/具体日期），取该日行程，
    再查当天真实天气，返回行程+天气的组合信息供生成提醒。

    Args:
        query: 用户关于行程/日期的提问，如"明天有什么安排，要注意什么"。
    """
    user_id = get_current_user_id()
    if user_id is None:
        return "当前未登录，无法查询行程。请先登录。"

    try:
        return await reminder.run(user_id, query)
    except Exception as exc:  # noqa: BLE001
        return f"行程查询失败：{exc}"


@tool
async def plan_trip(query: str) -> str:
    """根据出行需求自动排一份完整行程（含天气规避）。

    适用场景：用户说"周末想去广州玩两天""帮我排个三日游""怎么安排比较好"。
    内部会解析城市/天数/偏好，查真实逐日天气，再生成带时间的行程；
    **下雨或高温的日期不会安排户外活动**（生成后会做一次审计纠正）。

    Args:
        query: 用户的出行需求，如"周末想去广州玩两天，喜欢美食和拍照"。
    """
    if not query or not query.strip():
        return "请说明想去哪、几天，例如「周末想去广州玩两天」。"
    try:
        return await planner.run(query.strip())
    except Exception as exc:  # noqa: BLE001 排程失败要让用户看到原因而不是空白
        return f"排行程失败：{exc}"


def get_local_tools() -> list:
    """返回所有本地工具（进程内、带用户态）。"""
    return [search_my_plans, check_itinerary_weather, plan_trip]
