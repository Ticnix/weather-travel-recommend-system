"""图片文字识别（离线 OCR）：没有视觉模型时的兜底。

**为什么需要它**：视觉模型要 Key、要联网，而"用户发的图"里绝大多数是**截图**
（行程表、聊天记录、菜单、地图）。这类图用 OCR 抽文字 + 文本模型，就能直接回答，
而且完全离线、不花钱。

**边界（必须说清）**：OCR 只能读到"图上的字"，读不出"图里有什么"
（天空什么颜色、这是哪条街）。所以它只作为**降级路径**：
配了视觉模型就走视觉模型，没配才 OCR，且 OCR 没抽到字时如实告诉用户看不了图。

实现用 rapidocr-onnxruntime（开源、ONNX 运行时，无需 PyTorch，模型随包分发）。
未安装时返回空字符串——上层据此走"看不了图"的提示，而不是报错。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 单张图最多识别多少字，防止一张长截图把提示词撑爆
MAX_OCR_CHARS = 3000

_engine = None
_unavailable = False


def _get_engine():
    """懒加载 OCR 引擎（首次加载要 1~2 秒，不能每张图都重建）。"""
    global _engine, _unavailable
    if _unavailable:
        return None
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # 惰性导入：没装不影响其他功能
        except ImportError:
            logger.info("未安装 rapidocr-onnxruntime，图片将不做 OCR 兜底")
            _unavailable = True
            return None
        try:
            _engine = RapidOCR()
        except Exception as exc:  # noqa: BLE001 模型文件缺失等
            logger.warning("OCR 引擎初始化失败，后续图片不做 OCR: %s", exc)
            _unavailable = True
            return None
    return _engine


def available() -> bool:
    """OCR 是否可用（供健康检查/提示使用）。"""
    return _get_engine() is not None


def extract_text_sync(raw: bytes) -> str:
    """同步识别；失败或不可用时返回空字符串。"""
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        result, _elapsed = engine(raw)
    except Exception as exc:  # noqa: BLE001 识别失败不该让上传失败
        logger.warning("OCR 识别失败: %s", exc)
        return ""

    if not result:
        return ""
    # result 形如 [[box, text, score], ...]，按识别顺序拼接
    lines = [str(item[1]).strip() for item in result if len(item) > 1 and str(item[1]).strip()]
    text = "\n".join(lines)
    return text[:MAX_OCR_CHARS]


async def extract_text(raw: bytes) -> str:
    """异步版本（OCR 是 CPU 密集，放线程池避免阻塞事件循环）。"""
    import asyncio

    return await asyncio.to_thread(extract_text_sync, raw)
