from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 根目录（config.py 位于 backend/app/core/ 下，向上两级）
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """全局配置，从 .env 读取（DeepSeek Key 仅存后端 .env）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 数据库（asyncpg 异步驱动）
    DB_URL: str = "postgresql+asyncpg://admin:123456@127.0.0.1:5432/weather_db"
    # Redis
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    # ===== 多模型提供商配置（对话/生成）=====
    # 当前启用的对话模型提供商：deepseek / qwen / zhipu / openai / moonshot / ollama
    # 仅收录「OpenAI 兼容格式」的模型，避免引入不兼容适配器（如 Anthropic Claude）
    LLM_PROVIDER: str = "deepseek"
    # Agent 架构模式（Day 41）：
    #   single —— 单 Agent，意图分类 + 全量工具（旧架构）
    #   multi  —— Supervisor 多智能体，按领域分组工具、并行执行后汇总
    # 默认 single：新架构上线的第一步是"能一键回退"，
    # 出问题改一行配置就能退回旧路径，不用重新发版。
    AGENT_MODE: str = "single"

    # DeepSeek（对话/生成）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_LLM_MODEL: str = "deepseek-chat"

    # ===== 气象数据源 =====
    # 默认数据源：qweather（和风天气，国内本地化）/ open_meteo（兜底免费源）
    WEATHER_PROVIDER: str = "open_meteo"
    # 和风天气（QWeather）— 中国本地化、有官方预警
    QWEATHER_API_KEY: str = ""
    QWEATHER_BASE_URL: str = "https://devapi.qweather.com/v7"
    QWEATHER_DEFAULT_LOCATION: str = "101280101"  # 广州 LocationID

    # ===== MCP 配置 =====
    # 传输方式：stdio（本地开发，Agent 直接拉起 MCP Server 子进程）
    #          streamable_http（生产/上线，连接独立部署的 MCP Server）
    MCP_TRANSPORT: str = "stdio"
    # streamable_http 模式下 MCP Server 地址
    MCP_SERVER_URL: str = "http://127.0.0.1:9000/mcp"

    # ===== 联网搜索配置 =====
    # Tavily（AI 场景搜索引擎，优先）：免费注册 https://tavily.com 获取 Key
    TAVILY_API_KEY: str = ""
    # 是否启用 DuckDuckGo 兜底（Tavily 无 Key 或失败时自动降级）
    WEB_SEARCH_FALLBACK_DDG: bool = True

    # ===== 高德地图配置 =====
    # 高德开放平台 Web 服务 Key（个人开发者免费申请 https://lbs.amap.com）
    AMAP_API_KEY: str = ""
    AMAP_BASE_URL: str = "https://restapi.amap.com/v3"
    # 默认出发城市（地理编码时若地址不含城市，用此兜底）
    AMAP_DEFAULT_CITY: str = "广州"

    # 通义千问 Qwen（OpenAI 兼容，DashScope）
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_LLM_MODEL: str = "qwen-max"

    # 智谱 GLM（OpenAI 兼容，与 Embedding 同一 Key）
    ZHIPU_LLM_MODEL: str = "glm-4-plus"

    # OpenAI（原生 OpenAI 兼容）
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_LLM_MODEL: str = "gpt-4o-mini"

    # Moonshot Kimi（OpenAI 兼容）
    MOONSHOT_API_KEY: str = ""
    MOONSHOT_BASE_URL: str = "https://api.moonshot.cn/v1"
    MOONSHOT_LLM_MODEL: str = "moonshot-v1-8k"

    # Ollama 本地模型（OpenAI 兼容）
    OLLAMA_API_KEY: str = "ollama"  # 本地模型无需真实 Key，占位即可
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434/v1"
    OLLAMA_LLM_MODEL: str = "qwen2.5:7b"

    # 智谱 AI（Embedding）
    ZHIPU_API_KEY: str = ""
    ZHIPU_EMBED_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_EMBED_MODEL: str = "embedding-3"

    # JWT
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # 气象数据源（Open-Meteo，免费免 Key）
    WEATHER_API_BASE: str = "https://api.open-meteo.com/v1"
    # 历史归档接口（Day 42）：forecast 接口的 past_days 最多 92 天，
    # 拿不到去年同期数据，而同比分析必须有同期；archive 接口可回溯数十年
    WEATHER_ARCHIVE_BASE: str = "https://archive-api.open-meteo.com/v1"
    # 默认城市：广州 23.13°N, 113.26°E
    DEFAULT_CITY_CODE: str = "gz"
    DEFAULT_LATITUDE: float = 23.13
    DEFAULT_LONGITUDE: float = 113.26
    # 简易预警阈值（Open-Meteo 对中国无官方预警，按阈值兜底生成）
    RAIN_ALERT_MM: float = 10.0  # 24h 降水 ≥10mm 提示
    WIND_ALERT_KMH: float = 40.0  # 风速 ≥40km/h 提示

    # CSV 清洗模块
    UPLOAD_DIR: str = "uploads"  # 原始 CSV 存放目录（相对 backend 工作目录）
    CLEANED_DIR: str = "cleaned"  # 清洗结果 CSV 存放目录

    # RAG 知识库（Day6）
    KNOWLEDGE_DIR: str = "knowledge_base"  # 知识库文档目录（相对 backend 工作目录）
    EMBED_CHUNK_SIZE: int = 300  # 每个文本块的目标字符数
    EMBED_CHUNK_OVERLAP: int = 50  # 相邻块重叠字符数
    EMBED_BATCH_SIZE: int = 16  # 单次 embedding 批量大小
    EMBED_TIMEOUT: float = 30.0  # embedding 请求超时（秒）
    EMBED_DIM: int = 1024  # 向量维度（与智谱 embedding-3 dimensions=1024 对齐，匹配 Vector(1024)）
    EMBED_TOP_K: int = 5  # 检索返回的 TopK

    # ===== Web Push 通知（Day 34，VAPID 协议）=====
    VAPID_PRIVATE_KEY: str = ""  # base64url 编码的 P-256 私钥（不入库）
    VAPID_PUBLIC_KEY: str = ""  # 前端 subscribe 用的 applicationServerKey
    VAPID_CONTACT: str = "mailto:admin@weather-travel.local"  # 推送服务联系邮箱

    # ===== 邮件通道（SMTP 全部留空则通道自动禁用，发送时记为 skipped）=====
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
