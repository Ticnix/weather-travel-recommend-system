"""当前用户上下文（contextvars 实现）。

MCP 工具调用是「无状态」的，不携带用户身份。为让 search_my_plans 等
「用户私有」工具能知道当前是哪个用户在提问，用 contextvars 在请求链路中
透传 user_id，工具内部通过 get_current_user_id() 读取。

优势：不改 MCP 工具签名，Agent 层无感知，天然支持并发隔离。
"""

from __future__ import annotations

from contextvars import ContextVar, Token

# 当前请求的用户 ID（None 表示匿名）
_current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def set_current_user_id(user_id: int | None) -> Token:
    """设置当前请求的用户 ID，返回用于恢复的 token。"""
    return _current_user_id.set(user_id)


def reset_current_user_id(token: Token) -> None:
    """恢复用户 ID 到设置前的值（配合 set 返回的 token 使用）。"""
    _current_user_id.reset(token)


def get_current_user_id() -> int | None:
    """读取当前请求的用户 ID。"""
    return _current_user_id.get()