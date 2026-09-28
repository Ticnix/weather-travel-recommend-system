"""对话接口：单轮/多轮 AI 对话（LangGraph Agent + MCP 工具 + RAG + SSE 流式）+ 多模态附件。"""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.deps import CurrentUser, OptionalUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import agent, attachment_service, chat_history_service

router = APIRouter(prefix="/api/v1/chat", tags=["AI 对话"])


def _default_ask(items: list) -> str:
    """只发了附件、没写字时，替用户补一句得体的请求。

    没有这句，模型面对一份 PDF 只能干瞪眼（甚至反问"你想让我做什么"）。
    按附件类型给最合理的默认意图：图片要描述画面，文件/语音要总结要点。
    """
    kinds = {a.kind for a in items}
    if kinds == {"image"}:
        return "请描述这张图片的内容，并指出与出行相关的关键信息。"
    if "image" in kinds:
        return "请结合这些附件回答：图片描述画面，文件与语音总结要点。"
    if kinds == {"audio"}:
        return "请根据上面的语音内容回答。"
    return "请阅读上面的附件，简要总结它的内容与要点。"


async def _with_preferences(prompt: str, user_id: int | None) -> str:
    """把用户偏好拼进提示词（Day 55）。

    放在端点层而不是 _prepare_input：偏好只有登录用户才有，
    且单轮 / 流式两个端点都要注入——一处函数，两处调用。
    读取失败**绝不**拦对话：没有偏好只是回答少了针对性，
    对话挂了就是功能不可用。
    """
    if user_id is None:
        return prompt
    try:
        import logging

        from app.db.session import AsyncSessionLocal
        from app.services import user_preference

        async with AsyncSessionLocal() as db:
            data = await user_preference.get_data(db, user_id)
        block = user_preference.describe(data)
        return f"{prompt}\n\n{block}" if block else prompt
    except Exception:  # noqa: BLE001 偏好是增强，不是依赖
        logging.getLogger(__name__).warning("读取用户偏好失败，本轮不注入 user=%s", user_id)
        return prompt


async def _prepare_input(body: ChatRequest) -> tuple[str, list[str], str]:
    """把附件并进用户输入，返回 (提示词, 图片 dataURL, 落库用的用户消息)。

    附件过期/不支持的类型都直接 400 说清楚，而不是静默丢掉附件——
    "我明明传了文件，它却当没看见"是最难向用户解释的一种表现。
    """
    if not body.attachments:
        return body.message, [], body.message

    try:
        items = await attachment_service.load_many(body.attachments)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 只发了附件没写字：替用户补一句得体的请求。
    # 放服务端而不是前端——API 是公共入口，任何客户端只带附件调用时
    # 都该得到合理回答（否则模型面对一份 PDF 不知道要做什么）。
    typed = body.message.strip()
    message = typed or _default_ask(items)

    images = [a.data_url for a in items if a.kind == "image" and a.data_url]
    texts = [a for a in items if a.kind != "image"]
    names = "、".join(a.name for a in items)
    prompt = attachment_service.compose_prompt(message, texts)

    # 附件都在、却**没有任何可用内容**（例如图里没抽取到文字、视觉模型此刻不可用）：
    # 必须明确写出"这次没读到附件"，否则模型会顺口编一个原因——
    # 实测出现过"图片没能识别（视觉模型不可用）"这种凭空结论，用户看得一头雾水。
    if not images and not texts:
        prompt = (
            f"{prompt}\n\n【系统说明：本轮带了 {len(items)} 个附件（{names}），"
            "但服务端没有读到可用内容（可能是上传未成功、附件已过期，或该类型暂不可解析）。"
            "请如实请用户重新上传或改用文字描述，**不要猜测具体原因**。】"
        )

    # 历史里也留一份"带了什么附件"：多轮追问时模型才知道上文看过什么。
    # 用户只发了附件时不要伪造他的原话，直接标成"仅附件"更诚实。
    stored = f"{typed}（附件：{names}）" if typed else f"（仅附件：{names}）"
    return prompt, images, stored


@router.post("/attachments", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    file: Annotated[UploadFile, File(description="图片 / 语音 / 文档")],
    current: OptionalUser = None,
) -> dict:
    """上传对话附件，返回附件 id 与解析摘要。

    支持的输入：
    - 图片（jpg/png/webp/gif）→ 交给视觉模型
    - 语音（webm/mp3/wav/m4a/ogg）→ 先转写成文本（需配置 ASR，见 asr_service）
    - 文档（pdf/docx/xlsx/txt/md/csv/json）→ 抽成文本注入提示词

    附件不落盘、不落库：解析结果进 Redis（默认 30 分钟），发消息时按 id 引用。
    """
    raw = await file.read()
    try:
        _item, meta = await attachment_service.create(
            file.filename or "", file.content_type, raw
        )
    except ValueError as exc:
        # 这些消息都是写给用户看的（格式不支持 / 太大 / 语音未开启…）
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success(meta, message="附件已解析")


@router.post("", response_model=dict)
async def chat(body: ChatRequest, current: OptionalUser = None) -> dict:
    """单轮/多轮对话：意图识别 -> LLM 决策 -> MCP 工具/RAG -> 生成回答。

    可选鉴权：携带 token 时会把 user_id 传入 Agent，支持检索用户私有知识库
    并持久化多轮上下文；未登录则以匿名身份对话（仅公共能力，不记忆历史）。
    """
    user_id = current.id if current else None
    conversation_id = body.conversation_id or uuid.uuid4().hex[:16]

    prompt, images, stored_message = await _prepare_input(body)
    # 用户偏好注入（Day 55）：登录用户才生效，读取失败不拦对话
    prompt = await _with_preferences(prompt, user_id)

    # 读取历史（仅登录用户），构造多轮上下文
    history = await chat_history_service.get_recent_history(user_id, conversation_id)

    # 带图片时走视觉模型（不调工具，原因见 agent.chat_stream_with_images）
    result = (
        await agent.chat_with_images(prompt, images, history=history)
        if images
        else await agent.chat(prompt, user_id=user_id, history=history)
    )

    # 持久化本轮对话（登录用户）
    if user_id is not None:
        await chat_history_service.add_message(user_id, conversation_id, "user", stored_message)
        await chat_history_service.add_message(
            user_id, conversation_id, "assistant", result["answer"]
        )

    data = ChatResponse(**result).model_dump()
    data["conversation_id"] = conversation_id
    return success(data, message="对话完成")


@router.post("/stream")
async def chat_stream(body: ChatRequest, current: OptionalUser = None):
    """SSE 流式对话：逐 token 推送，打字机效果。

    事件格式：
      - data: {"type": "intent", "intent": "weather"}    # 意图
      - data: {"type": "token", "content": "广州今天"}   # token 片段（可多个）
      - data: {"type": "done"}                            # 结束

    携带 token 时同样支持多轮上下文与历史持久化。
    """
    user_id = current.id if current else None
    conversation_id = body.conversation_id or uuid.uuid4().hex[:16]
    prompt, images, stored_message = await _prepare_input(body)
    # 用户偏好注入（Day 55）：登录用户才生效，读取失败不拦对话
    prompt = await _with_preferences(prompt, user_id)
    history = await chat_history_service.get_recent_history(user_id, conversation_id)

    async def event_generator():
        full_answer = ""
        try:
            stream = (
                agent.chat_stream_with_images(prompt, images, history=history)
                if images
                else agent.chat_stream(prompt, user_id=user_id, history=history)
            )
            async for evt in stream:
                etype = evt.get("type")
                if etype == "token":
                    full_answer += evt.get("content", "")
                yield {"event": "message", "data": json.dumps(evt, ensure_ascii=False)}
        except Exception:  # noqa: BLE001
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "token", "content": "抱歉，AI 服务暂时不可用，请稍后重试。"},
                    ensure_ascii=False,
                ),
            }
        finally:
            # 流式结束后持久化（登录用户）
            if user_id is not None and full_answer:
                await chat_history_service.add_message(
                    user_id, conversation_id, "user", stored_message
                )
                await chat_history_service.add_message(
                    user_id, conversation_id, "assistant", full_answer
                )

    return EventSourceResponse(event_generator())


@router.get("/conversations", response_model=dict)
async def list_conversations(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """历史会话列表（需登录），按最后活跃时间倒序。

    此前只把消息存库供多轮上下文使用，没有对外读取接口，
    导致刷新页面后用户看不到任何历史对话。
    """
    items = await chat_history_service.list_conversations(current.id, db=db)
    return success({"items": items, "total": len(items)})


@router.get("/conversations/{conversation_id}", response_model=dict)
async def get_conversation(
    conversation_id: str,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """读取某个会话的全部消息（时间正序），供前端回放历史对话。"""
    items = await chat_history_service.get_conversation_messages(current.id, conversation_id, db=db)
    return success({"conversation_id": conversation_id, "items": items, "total": len(items)})


@router.delete("/conversations/{conversation_id}", response_model=dict)
async def delete_conversation(
    conversation_id: str,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """删除某个历史会话。"""
    deleted = await chat_history_service.delete_conversation(current.id, conversation_id, db=db)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="会话不存在")
    return success({"deleted": deleted}, message="会话已删除")
