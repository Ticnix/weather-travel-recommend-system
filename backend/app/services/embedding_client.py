"""智谱 AI Embedding 客户端。

调用智谱 ``embedding-3`` 模型生成向量，支持自定义维度（1024 维）。

- 生产环境：配置真实 ``ZHIPU_API_KEY`` 后走智谱真实 API，返回模型生成的 1024 维向量。
- 离线联调兜底：当 key 为空或 API 调用失败时，退化为确定性的本地伪向量
  （对文本做 n-gram hash 构造 1024 维），保证 RAG 检索链路在没有网络/Key 时
  也能完整跑通、维度恒为 1024。

智谱 Embedding API：
  POST https://open.bigmodel.cn/api/paas/v4/embeddings
  {"model": "embedding-3", "input": [...], "dimensions": 1024}
  Authorization: Bearer <ZHIPU_API_KEY>
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _local_pseudo_vector(text: str, dim: int) -> list[float]:
    """确定性伪向量：基于文本的字符 n-gram hash 构造，用于离线兜底。

    思路：把文本按固定滑动窗口切成若干子串，每个子串 hash 后映射到 [0, dim) 槽位，
    对槽位计数得到词袋式稀疏向量，再做 L2 归一化，保证相同/相似文本向量接近。
    """
    vec = [0.0] * dim
    ngram = 3
    text = text.lower()
    for i in range(len(text) - ngram + 1):
        token = text[i : i + ngram]
        digest = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        vec[idx] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


class EmbeddingClient:
    """智谱 AI Embedding 客户端。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.ZHIPU_API_KEY
        self.base_url = (base_url or settings.ZHIPU_EMBED_BASE_URL).rstrip("/")
        self.model = model or settings.ZHIPU_EMBED_MODEL
        self.dim = dim or settings.EMBED_DIM
        self.timeout = timeout or settings.EMBED_TIMEOUT

    @property
    def available(self) -> bool:
        """是否配置了真实 API Key（决定走真实接口还是本地兜底）。"""
        return bool(self.api_key) and not self.api_key.startswith("sk-xxxxxxxx")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。优先真实 API，失败/无 Key 时退化为本地伪向量。"""
        if not texts:
            return []
        if not self.available:
            logger.warning(
                "ZHIPU_API_KEY 未配置或为占位符，使用本地伪向量兜底（维度 %s）", self.dim
            )
            return [_local_pseudo_vector(t, self.dim) for t in texts]

        url = f"{self.base_url}/embeddings"
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dim,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            vectors = [item["embedding"] for item in data.get("data", [])]
            # 校验维度，防止与 Vector(1024) 不匹配报错
            for v in vectors:
                if len(v) != self.dim:
                    raise ValueError(f"向量维度 {len(v)} 与预期 {self.dim} 不一致")
            return vectors
        except Exception as exc:  # noqa: BLE001 网络/鉴权/维度异常统一降级
            logger.warning("智谱 Embedding 调用失败（%s），使用本地伪向量兜底", exc)
            return [_local_pseudo_vector(t, self.dim) for t in texts]


# 默认单例
embedding_client = EmbeddingClient()
