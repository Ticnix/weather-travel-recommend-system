import os
import sys
from pathlib import Path

BACKEND = Path(r"D:\myproject\weather-travel-recommend-system\backend")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

out = []
try:
    from app.services import knowledge_loader
    from app.services.rag_service import search
    from app.core.config import settings

    chunks = knowledge_loader.load_documents()
    out.append(f"docs_dir={settings.KNOWLEDGE_DIR} chunk_size={settings.EMBED_CHUNK_SIZE} overlap={settings.EMBED_CHUNK_OVERLAP}")
    out.append(f"total_chunks={len(chunks)}")
    by_src = {}
    for c in chunks:
        by_src.setdefault(c.source, []).append(c)
    out.append(f"documents={len(by_src)}")
    lens = [len(c.content) for c in chunks]
    out.append(f"chunk_len min={min(lens)} max={max(lens)} avg={sum(lens)//len(lens)}")
    for src in sorted(by_src):
        out.append(f"  {src}\tchunks={len(by_src[src])}\ttitle={by_src[src][0].title}")
    out.append("--- top5 sample ---")
    for c in chunks[:5]:
        out.append(f"  [{c.source}#{c.chunk_index}] {len(c.content)}字 :: {c.content[:60]!r}")
except Exception as exc:
    out.append(f"ERR: {type(exc).__name__}: {exc}")

Path(r"D:\myproject\weather-travel-recommend-system\.probe_s13_out.txt").write_text(
    "\n".join(out), encoding="utf-8"
)
