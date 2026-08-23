from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # DeepSeek（对话/生成）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_LLM_MODEL: str = "deepseek-chat"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
