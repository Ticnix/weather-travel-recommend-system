"""LLM 客户端：多提供商抽象层。

只收录「OpenAI 兼容格式」的对话模型，复用 langchain-openai 的 ChatOpenAI，
通过切换 base_url / api_key / model 即可对接不同厂商，避免引入不兼容适配器。

支持的提供商（均 OpenAI 兼容）：
- deepseek : DeepSeek
- qwen     : 通义千问（DashScope）
- zhipu    : 智谱 GLM（与 Embedding 共用 Key）
- openai   : OpenAI
- moonshot : Moonshot Kimi
- ollama   : 本地模型（Ollama）

用法：
- get_llm():            返回当前默认提供商（settings.LLM_PROVIDER）的实例
- get_llm(provider):    返回指定提供商的实例（多实例缓存，互不影响）
- ainvoke():            异步单轮对话，返回模型文本输出
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# 提供商 → 配置字段名映射（api_key / base_url / model）
# 仅维护 OpenAI 兼容提供商，保证 get_llm 逻辑统一、无需分支特殊处理
_PROVIDERS: dict[str, tuple[str, str, str]] = {
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_LLM_MODEL"),
    "qwen": ("QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_LLM_MODEL"),
    "zhipu": ("ZHIPU_API_KEY", "ZHIPU_EMBED_BASE_URL", "ZHIPU_LLM_MODEL"),
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_LLM_MODEL"),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL", "MOONSHOT_LLM_MODEL"),
    "ollama": ("OLLAMA_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_LLM_MODEL"),
}

# 多实例缓存：provider -> ChatOpenAI，避免每次调用重复实例化
_llm_cache: dict[str, ChatOpenAI] = {}


def _resolve_provider(provider: str) -> tuple[str, str, str]:
    """解析提供商的 api_key / base_url / model 三个配置值。"""
    if provider not in _PROVIDERS:
        supported = ", ".join(_PROVIDERS)
        raise ValueError(f"不支持的模型提供商: {provider}（可选: {supported}）")

    key_field, url_field, model_field = _PROVIDERS[provider]
    api_key = getattr(settings, key_field, "")
    base_url = getattr(settings, url_field, "")
    model = getattr(settings, model_field, "")
    return api_key, base_url, model


def get_llm(provider: str | None = None, **kwargs: Any) -> ChatOpenAI:
    """按提供商获取（并缓存）ChatOpenAI 实例。

    参数：
    - provider: 提供商名，默认取 settings.LLM_PROVIDER
    - kwargs: 透传 ChatOpenAI 额外参数（如 temperature / timeout），便于调用方覆盖

    说明：
    - 同一提供商只实例化一次，缓存在 _llm_cache
    - 不同提供商各自独立缓存，切换 provider 互不影响
    """
    provider = (provider or settings.LLM_PROVIDER).lower()
    api_key, base_url, model = _resolve_provider(provider)

    cache_key = provider
    if cache_key not in _llm_cache:
        if not api_key:
            # 未配置 Key 时用占位符实例化，避免实例化即抛异常；
            # 真正调用时才报鉴权错误，由上层（LangGraph 兜底节点）统一处理。
            logger.warning("提供商 %s 未配置 API Key，实际调用将失败", provider)
            api_key = "sk-placeholder"
        _llm_cache[cache_key] = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.3,
            timeout=60.0,
            max_retries=2,
            **kwargs,
        )
    return _llm_cache[cache_key]


async def ainvoke(prompt: str, system: str | None = None, provider: str | None = None) -> str:
    """异步单轮对话，返回模型文本输出。

    网络异常 / 限流 / 鉴权失败时抛出异常，由调用方（LangGraph 节点）统一兜底。
    """
    llm = get_llm(provider)
    messages: list[tuple[str, str]] = []
    if system:
        messages.append(("system", system))
    messages.append(("human", prompt))

    resp = await llm.ainvoke(messages)
    return resp.content if isinstance(resp.content, str) else str(resp.content)
