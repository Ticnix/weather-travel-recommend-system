"""语音转写（ASR）：可插拔后端。

**为什么做成多后端**：「哪个能用」取决于部署环境，而不是代码本身——
- `openai`：任何 OpenAI 兼容的 `/audio/transcriptions`。智谱、通义、自建
  vLLM/Speaches 都能提供，有 Key 就能立刻用，不必下载模型。
- `faster_whisper`：完全本地开源（MIT，基于 CTranslate2 的 Whisper 重构），
  不依赖外部网络，但首次运行要下载模型、推理吃 CPU。
- `none`（默认）：宁可明确说「未开启语音转写」，也不要假装支持然后返回空字符串——
  后者用户只会以为"识别不出来"，而不知道该去开配置。
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 本地模型实例缓存：加载一次模型要几秒，不能每次请求都重载
_whisper_model = None


def _llm_credentials() -> tuple[str, str]:
    """ASR 未单独配置时，复用当前 LLM 提供商的 base_url / api_key。"""
    from app.services.llm_client import _resolve_provider  # 复用同一套配置解析

    provider = (settings.LLM_PROVIDER or "deepseek").lower()
    api_key, base_url, _model = _resolve_provider(provider)
    return settings.ASR_BASE_URL or base_url, settings.ASR_API_KEY or api_key


async def _transcribe_openai(raw: bytes, filename: str, mime: str) -> str:
    base_url, api_key = _llm_credentials()
    if not base_url or not api_key:
        raise ValueError("未配置语音转写服务（ASR_BASE_URL / ASR_API_KEY）")
    url = base_url.rstrip("/") + "/audio/transcriptions"
    files = {"file": (filename or "voice.webm", raw, mime or "audio/webm")}
    data = {"model": settings.ASR_MODEL}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, files=files, data=data, headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:200]
        raise ValueError(f"语音转写服务返回 {exc.response.status_code}：{body}") from exc
    except Exception as exc:  # noqa: BLE001 网络问题不该让整个上传 500
        raise ValueError(f"语音转写服务不可用：{type(exc).__name__}") from exc

    text = (payload.get("text") or "").strip()
    if not text:
        raise ValueError("语音转写没有返回内容，可能是录音太短或没有语音")
    return text


def _transcribe_local_sync(raw: bytes) -> str:
    global _whisper_model
    try:
        from faster_whisper import WhisperModel  # 惰性导入：未安装时给明确提示
    except ImportError as exc:
        raise ValueError(
            "服务端未安装 faster-whisper（pip install faster-whisper），"
            "或把 ASR_PROVIDER 改为 openai 使用云端转写"
        ) from exc

    if _whisper_model is None:
        logger.info("加载本地语音模型 %s（首次较慢）", settings.ASR_LOCAL_MODEL)
        _whisper_model = WhisperModel(settings.ASR_LOCAL_MODEL, device="cpu", compute_type="int8")

    # 浏览器录的是 webm/opus，faster-whisper（PyAV 解码）能直接吃容器格式。
    # 但**必须包成文件对象**：直接传 bytes 会被当成文件路径，
    # 报 "File object has no read() method, or readable() returned False"
    # ——这个错只有真正跑一次语音才会出现，所以务必保持 io.BytesIO 包装。
    import io

    try:
        segments, _info = _whisper_model.transcribe(
            io.BytesIO(raw), language="zh", vad_filter=True
        )
        text = "".join(segment.text for segment in segments).strip()
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 解码失败 ≠ 服务坏了，要说清是哪一步
        raise ValueError(
            f"语音解码失败（{type(exc).__name__}）：录音格式可能不受支持或文件损坏，请重新录一段"
        ) from exc

    if not text:
        raise ValueError("没有识别到语音内容，可能是录音太短或环境噪声过大")
    return text


async def _transcribe_local(raw: bytes) -> str:
    # CPU 密集：放线程池，避免阻塞事件循环（其他请求会被一起卡住）
    return await asyncio.to_thread(_transcribe_local_sync, raw)


async def transcribe(raw: bytes, filename: str = "", mime: str = "") -> str:
    """把一段音频转成文字；不可用时抛 ValueError（消息直接可展示给用户）。"""
    provider = (settings.ASR_PROVIDER or "none").strip().lower()
    if provider == "none":
        raise ValueError(
            "服务端未开启语音转写：可以先用文字描述，"
            "或配置 ASR_PROVIDER=openai（云端） / faster_whisper（本地开源）后再试"
        )
    if provider == "openai":
        return await _transcribe_openai(raw, filename, mime)
    if provider in ("faster_whisper", "faster-whisper", "local"):
        return await _transcribe_local(raw)
    raise ValueError(f"不支持的 ASR_PROVIDER：{provider}")
