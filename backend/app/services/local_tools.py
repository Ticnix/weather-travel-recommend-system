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


def get_local_tools() -> list:
    """返回所有本地工具（进程内、带用户态）。"""
    return [search_my_plans]