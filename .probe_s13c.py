import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(r"D:\myproject\weather-travel-recommend-system\backend")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.services.embedding_client import embedding_client
from app.services.knowledge_loader import load_documents

out = []


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


async def main():
    chunks = load_documents()
    out.append(f"total chunks = {len(chunks)}  embedding.available={embedding_client.available}")
    vecs = await embedding_client.embed_texts([c.content for c in chunks])

    queries = [
        "明天爬白云山穿什么",
        "广州哪里有好吃的早茶",
        "下雨天适合去哪里玩",
        "从广州塔怎么去珠江新城",
    ]
    for q in queries:
        qv = (await embedding_client.embed_texts([q]))[0]
        scored = sorted(
            ((round(cos(qv, v), 4), i) for i, v in enumerate(vecs)), reverse=True
        )[:3]
        out.append(f"\nQ: {q}")
        for s, i in scored:
            c = chunks[i]
            out.append(f"   {s}  [{c.source}#{c.chunk_index}] {c.content[:70]!r}")

    # 跨文档重复度：不同文档里是否出现近乎一样的块
    out.append("\n--- 近重复块（相似度 >= 0.9 的块对，只列前 10 对）---")
    pairs = []
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            s = cos(vecs[i], vecs[j])
            if s >= 0.9:
                pairs.append((round(s, 4), chunks[i].source, chunks[j].source, chunks[i].chunk_index, chunks[j].chunk_index))
    pairs.sort(reverse=True)
    out.append(f"pairs>=0.9: {len(pairs)}")
    for p in pairs[:10]:
        out.append(f"   {p[0]}  {p[1]}#{p[3]}  <->  {p[2]}#{p[4]}")


asyncio.run(main())
Path(r"D:\myproject\weather-travel-recommend-system\.probe_s13c_out.txt").write_text(
    "\n".join(out), encoding="utf-8"
)
