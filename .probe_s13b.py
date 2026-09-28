import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(r"D:\myproject\weather-travel-recommend-system\backend")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.services.embedding_client import embedding_client
from app.services.knowledge_loader import split_text

out = []


def fake_vec(text: str, dim: int = 1024):
    return embedding_client._local_pseudo_vector(text, dim) if False else None


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


async def main():
    out.append(f"embedding.available = {embedding_client.available}")
    out.append(f"dim = {embedding_client.dim}")

    # 取真实文档
    doc = Path("knowledge_base/guangzhou_transport.md").read_text(encoding="utf-8")
    chunks = split_text(doc, 300, 50)
    out.append(f"transport chunks = {len(chunks)}")
    for i, c in enumerate(chunks):
        out.append(f"  #{i} {len(c)}字 :: {c[:50]!r}")

    # 用本地伪向量看检索效果（离线可复现）
    texts = chunks
    vecs = await embedding_client.embed_texts(texts)
    for q in ["广州地铁怎么坐", "打车难不难", "去沙面岛骑车"]:
        qv = (await embedding_client.embed_texts([q]))[0]
        scored = sorted(
            ((round(cos(qv, v), 4), i) for i, v in enumerate(vecs)), reverse=True
        )
        out.append(f"query {q!r} -> " + ", ".join(f"#{i}({s})" for s, i in scored))


asyncio.run(main())
Path(r"D:\myproject\weather-travel-recommend-system\.probe_s13b_out.txt").write_text(
    "\n".join(out), encoding="utf-8"
)
