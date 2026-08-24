"""Agent 端 MCP 客户端封装。

负责把 MCP Server 暴露的工具加载成 LangChain 可直接调用的 tool。

两种模式（通过 settings.MCP_TRANSPORT 切换）：
- stdio          : 本地开发，Agent 直接拉起 MCP Server 子进程（进程内通信）
- streamable_http: 生产/上线，连接独立部署的 MCP Server（HTTP 通信）

工具与 Agent 解耦：Agent 不关心工具具体实现，只通过 MCP 协议动态发现。
以后增删工具，Agent 端零改动（重启后自动重新发现）。
"""

from __future__ import annotations

import logging
import sys

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StdioConnection, StreamableHttpConnection

from app.core.config import BACKEND_DIR, settings

logger = logging.getLogger(__name__)

# 工具缓存：进程内只加载一次，避免每次对话都重新拉起 MCP Server
_client: MultiServerMCPClient | None = None
_tools_cache: list[BaseTool] | None = None


def _build_connection() -> dict:
    """根据配置构造 MCP 连接。"""
    if settings.MCP_TRANSPORT == "streamable_http":
        return {
            "transport": "streamable_http",
            "url": settings.MCP_SERVER_URL,
        }
    # 默认 stdio：本地拉起 MCP Server 子进程
    # 注意：用当前进程的 sys.executable（即 venv 的 Python），
    # 否则系统 Python 没有安装 mcp 包，会导致 ModuleNotFoundError
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "mcp_server.server"],
        "cwd": str(BACKEND_DIR),  # 确保相对 import 生效
    }


def _get_client() -> MultiServerMCPClient:
    """获取（并缓存）MCP 客户端。"""
    global _client
    if _client is None:
        connection = _build_connection()
        _client = MultiServerMCPClient(
            connections={"weather_travel": connection},
            handle_tool_errors=True,  # 工具出错时返回错误文本而非抛异常
        )
        logger.info("MCP 客户端已初始化（transport=%s）", settings.MCP_TRANSPORT)
    return _client


async def get_mcp_tools() -> list[BaseTool]:
    """加载 MCP Server 暴露的所有工具（缓存，幂等）。"""
    global _tools_cache
    if _tools_cache is None:
        client = _get_client()
        _tools_cache = await client.get_tools()
        logger.info("已加载 %d 个 MCP 工具: %s", len(_tools_cache), [t.name for t in _tools_cache])
    return _tools_cache


async def reload_tools() -> list[BaseTool]:
    """强制重新加载工具（用于 MCP Server 重启后同步）。"""
    global _tools_cache
    _tools_cache = None
    return await get_mcp_tools()