"""MCP Server：天气出行助手工具服务。

采用 FastMCP 注册 3 个工具，支持两种运行模式（通过命令行参数切换）：

1. stdio（本地开发，默认）
   python -m mcp_server.server

2. Streamable HTTP（生产/上线）
   python -m mcp_server.server --transport streamable-http --port 9000
   Agent 通过 http://<host>:9000/mcp 连接

工具与 Agent 解耦：本服务可独立部署、独立扩容，Agent 通过 MCP 协议动态发现工具。
以后增删工具只需修改本文件 + tools.py，Agent 端零改动。
"""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from mcp_server import tools

# 创建 MCP 服务实例
mcp = FastMCP(
    name="weather-travel-tools",
    instructions=(
        "天气出行助手工具服务，提供实时天气、天气预报、资讯检索三类能力。"
        "城市名支持中文名、拼音、常见别名。"
    ),
)


# ===== 工具注册 =====
# 每个工具用 @mcp.tool() 装饰，参数说明直接写在 docstring 里，Agent 会自动读取并理解


@mcp.tool()
async def get_weather(city: str) -> str:
    """查询指定城市的实时天气（当前温度、体感、湿度、风向风力、降水、能见度等）。

    Args:
        city: 城市名，支持中文名/拼音/别名，如"广州"、"北京"、"gz"、"上海"。
    """
    return await tools.get_weather(city)


@mcp.tool()
async def get_forecast(city: str, days: int = 3) -> str:
    """查询指定城市未来 N 天（1~7 天）的天气预报，含温度区间、天气现象、降水与预警。

    Args:
        city: 城市名，支持中文名/拼音/别名。
        days: 预报天数，1~7 之间的整数，默认 3 天。
    """
    return await tools.get_forecast(city, days)


@mcp.tool()
async def search_news(keyword: str, category: str = "", limit: int = 5) -> str:
    """从资讯库检索相关资讯（公告/出行/穿搭等）。

    Args:
        keyword: 检索关键词，如"台风"、"高铁"、"穿搭"。
        category: 资讯类别，可选 notice（公告）/travel（出行）/outfit（穿搭），留空则不限类别。
        limit: 返回条数，1~10，默认 5。
    """
    return await tools.search_news(keyword, category or None, limit)


@mcp.tool()
async def search_knowledge(query: str, top_k: int = 5) -> str:
    """从知识库（RAG 向量检索）语义检索相关内容，覆盖广州气候/美食/交通/景点/穿搭/天气出行规划等。

    Args:
        query: 用户问题的自然语言描述，如"广州塔怎么去"、"下雨天穿什么"。
        top_k: 返回条数，1~10，默认 5。
    """
    return await tools.search_knowledge(query, top_k)


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> str:
    """联网搜索实时信息（Tavily 优先、DuckDuckGo 兜底）。

    用于回答知识库和天气 API 都覆盖不到的实时/时效性问题，
    如"广州塔今天开放吗""最近广州有什么活动""某景区最新门票"。

    Args:
        query: 搜索关键词或问题，如"广州塔 开放时间 2026"。
        max_results: 返回条数，1~10，默认 5。
    """
    return await tools.web_search(query, max_results)


@mcp.tool()
async def plan_travel_route(origin: str, destination: str, city: str = "广州") -> str:
    """出行规划：从出发地到目的地，返回多套出行方案（驾车/公交/步行/骑行等），
    融合时间、费用、天气三个维度综合评分排序，并附带天气提示。

    Args:
        origin: 出发地，如"广州南站"。
        destination: 目的地，如"广州塔"。
        city: 所在城市，默认"广州"。
    """
    return await tools.plan_travel_route(origin, destination, city)


@mcp.tool()
async def recommend_outfit(city: str = "广州", scene: str = "", preference: str = "") -> str:
    """穿搭推荐：结合天气（温度/降水/风）+ 活动场景 + 用户偏好，生成贴合场景的穿搭建议。

    适用"明天爬山穿什么""下雨天逛街穿什么""我怕冷怎么穿"等。

    Args:
        city: 城市，默认"广州"。
        scene: 活动场景（爬山/逛街/夜游/商务/通勤/露营/骑行/观景/亲子/摄影），可留空。
        preference: 用户偏好（怕冷/怕热/正式/运动/休闲/简约/时尚），可留空。
    """
    return await tools.recommend_outfit(city, scene, preference)


def main() -> None:
    """命令行入口：解析 --transport 选择运行模式。"""
    parser = argparse.ArgumentParser(description="MCP 天气出行工具服务")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="传输方式：stdio（本地）/ streamable-http（上线）",
    )
    parser.add_argument("--port", type=int, default=9000, help="HTTP 端口（默认 9000）")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 监听地址")
    args = parser.parse_args()

    if args.transport == "streamable-http":
        # 生产模式：独立 HTTP 服务，Agent 通过 /mcp 端点连接
        mcp.run_streamable_http(host=args.host, port=args.port)
    else:
        # 本地开发：stdio 标准输入输出
        mcp.run()


if __name__ == "__main__":
    main()
