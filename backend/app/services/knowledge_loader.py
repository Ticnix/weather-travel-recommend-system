"""知识库文档加载与重叠分块器。

职责：
- 扫描 knowledge_base 目录下的 .md/.txt 文档
- 按标题切分文档为章节，再按目标字符数 + 重叠进行分块
- 返回统一的 TextChunk 结构，供 embedding 入库使用
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings


@dataclass
class TextChunk:
    """单个文本块。"""

    title: str  # 文档标题（用于检索展示与溯源）
    source: str  # 来源文件名
    chunk_index: int  # 文档内分块序号
    content: str  # 块内容


def _extract_title(text: str, filename: str) -> str:
    """取文档首个一级标题作为标题，否则用文件名。"""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return Path(filename).stem


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """把一段长文本按重叠滑窗切块。

    以段落（\n\n）为单位尽量在句子边界切分；单个超长段落内部按字符滑窗硬切。
    相邻块之间保留 overlap 字符，避免切断语义边界导致信息丢失。
    """
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    # 先按空行分段，尽量保证语义完整
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
                current = current[-overlap:] if overlap > 0 else ""  # 保留重叠
            # 处理超长段落：滑窗硬切
            if len(para) > chunk_size:
                i = 0
                while i < len(para):
                    end = min(i + chunk_size, len(para))
                    chunks.append(para[i:end].strip())
                    i = end - overlap if end < len(para) else len(para)
            else:
                current = para
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


def load_documents(directory: str | Path | None = None) -> list[TextChunk]:
    """加载知识库目录下所有文档并分块。

    Returns:
        所有文档分块后的 TextChunk 列表。
    """
    directory = Path(directory or settings.KNOWLEDGE_DIR)
    chunk_size = settings.EMBED_CHUNK_SIZE
    overlap = settings.EMBED_CHUNK_OVERLAP

    if not directory.is_dir():
        raise FileNotFoundError(f"知识库目录不存在：{directory}")

    chunks: list[TextChunk] = []
    files = sorted(directory.glob("*"))
    for file in files:
        if not file.is_file() or file.suffix.lower() not in {".md", ".txt"}:
            continue
        text = file.read_text(encoding="utf-8")
        title = _extract_title(text, file.name)
        parts = split_text(text, chunk_size, overlap)
        for idx, part in enumerate(parts):
            chunks.append(TextChunk(title=title, source=file.name, chunk_index=idx, content=part))
    return chunks
