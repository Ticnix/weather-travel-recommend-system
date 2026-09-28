"""对话附件：图片 / 语音 / 文件（多模态对话的支撑层）。

**为什么"不落库、不落盘"**：附件只是这一轮对话的上下文，没有长期价值。
解析结果放 Redis、30 分钟过期、用完即弃，于是既不用加表（本项目用 create_all，
新增列不会自动迁到老库），也不用写清理任务。
代价是 Redis 不可用时附件整体不可用——这是**明确报错**的取舍，
比"悄悄丢掉附件、让模型答非所问"要好。

三类附件走三条路：
- 图片：保留 base64 交给视觉模型（不再做 OCR，视觉模型本身就能读图上的字）
- 语音：先用可插拔 ASR 转写（见 asr_service），再当文本处理
- 文件：抽成纯文本注入提示词
"""

from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Any

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.services import asr_service, ocr_service

logger = logging.getLogger(__name__)

IMAGE_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}

# 浏览器给 content-type 有时是 application/octet-stream，按扩展名兜底
_EXT_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".webm": "audio/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".log": "text/plain",
}

_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".log", ".yml", ".yaml"}
_PLAIN_MIMES = {"text/plain", "text/markdown", "text/csv", "application/json"}

# 单条消息可带的附件数量上限：再多也不会有人看，还会把提示词撑爆
MAX_ATTACHMENTS = 5
# 注入提示词的正文总上限（单条 ATTACHMENT_MAX_CHARS，合计不超过这个数）
_TOTAL_CHARS = 12000


@dataclass
class Attachment:
    """一个已解析的附件。text 与 data_url 按 kind 二选一。"""

    id: str
    kind: str  # image / audio / document
    name: str
    mime: str
    size: int
    text: str | None = None
    data_url: str | None = None


def _mime_of(filename: str, content_type: str | None) -> str:
    lowered = (filename or "").lower()
    for ext, mime in _EXT_MIME.items():
        if lowered.endswith(ext):
            return mime
    return (content_type or "application/octet-stream").split(";")[0].strip().lower()


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # 惰性导入：没装这个库时只影响这一种格式
        raise ValueError("服务端未安装 pypdf，暂不支持 PDF 解析") from exc

    reader = PdfReader(BytesIO(raw))
    chunks: list[str] = []
    # 只读前 40 页：超大 PDF 既慢又会把提示词撑爆，超出部分明确告知
    for index, page in enumerate(reader.pages[:40], start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 个别页解析失败不该让整份文件失败
            text = ""
        if text.strip():
            chunks.append(f"[第 {index} 页]\n{text}")
    if not chunks:
        raise ValueError("这个 PDF 没有可提取的文字（可能是扫描件图片，需 OCR）")
    if len(reader.pages) > 40:
        chunks.append(f"（仅解析前 40 页，共 {len(reader.pages)} 页）")
    return "\n\n".join(chunks)


def _extract_docx(raw: bytes) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:
        raise ValueError("服务端未安装 python-docx，暂不支持 Word 文档") from exc

    document = docx.Document(BytesIO(raw))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    # 表格里的信息往往才是重点（行程表、费用表）
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    if not parts:
        raise ValueError("这个 Word 文档没有可提取的文字")
    return "\n".join(parts)


def _extract_xlsx(raw: bytes) -> str:
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("服务端未安装 openpyxl，暂不支持 Excel 文件") from exc

    book = openpyxl.load_workbook(BytesIO(raw), read_only=True, data_only=True)
    chunks: list[str] = []
    for sheet in book.worksheets[:5]:  # 最多 5 个工作表
        rows: list[str] = []
        for row in sheet.iter_rows(max_row=200, values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(cell.strip() for cell in cells):
                rows.append(" | ".join(cells))
        if rows:
            chunks.append(f"[工作表：{sheet.title}]\n" + "\n".join(rows))
    book.close()
    if not chunks:
        raise ValueError("这个 Excel 里没有可提取的内容")
    return "\n\n".join(chunks)


def _extract_text(filename: str, mime: str, raw: bytes) -> str:
    """按扩展名/类型抽文本。不支持的格式明确报错，而不是返回空字符串。"""
    lowered = (filename or "").lower()
    if lowered.endswith(".pdf") or mime == "application/pdf":
        return _extract_pdf(raw)
    if lowered.endswith(".docx"):
        return _extract_docx(raw)
    if lowered.endswith(".xlsx"):
        return _extract_xlsx(raw)
    if lowered.endswith(".doc") or lowered.endswith(".xls"):
        raise ValueError("不支持老版 .doc/.xls，请另存为 .docx/.xlsx 后再上传")
    if mime in _PLAIN_MIMES or any(lowered.endswith(ext) for ext in _TEXT_EXTS):
        for encoding in ("utf-8", "gb18030"):  # 中文文本文件常见 GBK/GB18030
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("文本文件编码无法识别（建议保存为 UTF-8）")
    raise ValueError(f"暂不支持这种文件类型：{filename or mime}")


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    text = text.strip()
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _vision_available() -> bool:
    """配置的视觉提供商是否**真的可用**。

    有视觉模型就不走 OCR：视觉模型能读懂"图里有什么"，
    而 OCR 只能读出图上的字——它是**降级路径**，不是替代品。

    但"配了 Key"不等于"Key 能用"：Key 过期/复制不全时，上游会 401。
    这种情况必须退回 OCR（见 llm_client.vision_broken_reason），
    否则用户每张图都失败，比不配 Key 还糟。
    """
    from app.services.llm_client import _resolve_provider, vision_broken_reason

    if vision_broken_reason():
        return False

    provider = (settings.VISION_PROVIDER or settings.LLM_PROVIDER or "").lower()
    if provider == "ollama":  # 本地模型：密钥只是占位符，不能按"非空即可用"判断
        return True
    try:
        api_key, _base_url, _model = _resolve_provider(provider)
    except ValueError:
        return False
    return bool(api_key)


async def create(filename: str, content_type: str | None, raw: bytes) -> tuple[Attachment, dict[str, Any]]:
    """解析一个上传的附件并暂存，返回 (附件对象, 给前端的元信息)。"""
    if not raw:
        raise ValueError("文件是空的")
    if len(raw) > settings.ATTACHMENT_MAX_BYTES:
        # 报出"实际多大 / 上限多少"：只说"超过上限"用户没法判断要不要压缩。
        # 前端已做上传前压缩（utils/prepareUpload.ts），这里兜住直接调接口的情况。
        limit_mb = settings.ATTACHMENT_MAX_BYTES // 1024 // 1024
        raise ValueError(
            f"原文件 {len(raw) / 1024 / 1024:.1f}MB，超过 {limit_mb}MB 上限。"
            "手机拍的原图/微信原图常超过这个体积，可先压缩或改用截图再上传"
        )

    mime = _mime_of(filename, content_type)
    name = filename or f"未命名.{mime.split('/')[-1]}"
    aid = uuid.uuid4().hex[:16]

    if mime in IMAGE_MIMES:
        if _vision_available():
            item = Attachment(
                id=aid,
                kind="image",
                name=name,
                mime=mime,
                size=len(raw),
                data_url=f"data:{mime};base64,{base64.b64encode(raw).decode()}",
            )
            preview = "图片已上传，将交给视觉模型识别"
        else:
            # 没配视觉模型：先用**离线 OCR** 兜底。
            # 用户发的图里绝大多数是截图（行程表、聊天记录、地图），
            # 这类图抽到文字就能直接答，不必等用户去申请 Key。
            ocr_text = (await ocr_service.extract_text(raw)).strip()
            if ocr_text:
                body, cut = _truncate(ocr_text, settings.ATTACHMENT_MAX_CHARS)
                item = Attachment(
                    id=aid, kind="document", name=name, mime=mime, size=len(raw), text=body
                )
                preview = f"未配置视觉模型，已用 OCR 识别出 {len(body)} 字" + (
                    "（已截断）" if cut else ""
                )
            else:
                # 图里既没文字、又没有视觉模型：如实说明，并给出怎么开启
                item = Attachment(
                    id=aid,
                    kind="image",
                    name=name,
                    mime=mime,
                    size=len(raw),
                    data_url=f"data:{mime};base64,{base64.b64encode(raw).decode()}",
                )
                preview = "图里没识别到文字，且未配置视觉模型"
    elif mime.startswith("audio/"):
        # ASR 不可用时抛的是 ValueError，消息本身就是给用户看的
        text = await asr_service.transcribe(raw, name, mime)
        body, cut = _truncate(text, settings.ATTACHMENT_MAX_CHARS)
        item = Attachment(id=aid, kind="audio", name=name, mime=mime, size=len(raw), text=body)
        preview = f"语音已转写：{body[:40]}{'…' if len(body) > 40 else ''}"
        if cut:
            preview += "（内容较长，已截断）"
    else:
        text = _extract_text(name, mime, raw)
        body, cut = _truncate(text, settings.ATTACHMENT_MAX_CHARS)
        item = Attachment(id=aid, kind="document", name=name, mime=mime, size=len(raw), text=body)
        preview = f"已解析 {len(body)} 字" + ("（已截断）" if cut else "")
        if not body:
            raise ValueError("文件里没有可用的文字内容")

    payload = asdict(item)
    key = f"chat:attachment:{aid}"
    await cache_set(key, payload, settings.ATTACHMENT_TTL_SECONDS)
    # cache_set 失败是静默的（缓存层的设计如此），这里回读一次确认：
    # 否则用户上传成功、发消息时才报"附件已过期"，最难排查
    if await cache_get(key) is None:
        raise ValueError("附件暂存失败（缓存不可用），请稍后重试或改用文字描述")

    meta: dict[str, Any] = {
        "id": aid,
        "kind": item.kind,
        "name": name,
        "mime": mime,
        "size": item.size,
        "preview": preview,
        "chars": len(item.text or ""),
    }
    return item, meta


async def load_many(ids: list[str]) -> list[Attachment]:
    """按 id 取回附件；过期/不存在时明确报错（而不是当作没有附件）。"""
    items: list[Attachment] = []
    for aid in (ids or [])[:MAX_ATTACHMENTS]:
        data = await cache_get(f"chat:attachment:{aid}")
        if data is None:
            raise ValueError("附件已过期（超过 30 分钟）或不存在，请重新上传")
        items.append(Attachment(**data))
    return items


def compose_prompt(message: str, texts: list[Attachment]) -> str:
    """把附件正文拼进用户输入。

    超出上限就**明确写出"已截断"**：让模型和用户都知道信息不全，
    比悄悄丢掉后半段、然后答出一个漏掉关键条件的结论要好。
    """
    if not texts:
        return message

    blocks: list[str] = []
    used = 0
    for item in texts:
        body = (item.text or "").strip()
        if not body:
            continue
        label = "语音转写" if item.kind == "audio" else "附件"
        remain = _TOTAL_CHARS - used
        if remain <= 0:
            blocks.append(f"【{label}：{item.name}】（内容过多，已省略）")
            continue
        piece = body[:remain]
        used += len(piece)
        note = "，已截断" if len(piece) < len(body) else ""
        blocks.append(f"【{label}：{item.name}（{len(piece)} 字{note}）】\n{piece}")

    return f"{message}\n\n" + "\n\n".join(blocks)
