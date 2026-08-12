"""智能客服对话接口（08 §4.4 / 03）：SSE 流式对话 + 会话恢复。"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import chat_graph
from app.agents.state import ChatState
from app.api.deps import get_db, require_roles
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.rag.retriever import filter_accessible_kb_ids
from app.schemas.chat import (
    ChatRequest,
    MessageOut,
    SessionDetailOut,
    SessionOut,
)
from app.services import model_profile_service, session_service

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _emit(queue: asyncio.Queue, event: str, data: dict) -> None:
    queue.put_nowait({"event": event, "data": data})


async def _run_chat_pipeline(
    payload: ChatRequest, user: User, queue: asyncio.Queue
) -> None:
    """对话主流程：会话恢复/新建 → 持久化 → 图执行 → 结果落库 → 事件推送。"""
    from app.db.session import get_session_factory

    request_id = str(uuid.uuid4())
    async with get_session_factory()() as db:
        try:
            accessible = await filter_accessible_kb_ids(db, payload.kb_ids)
            if not accessible:
                _emit(queue, "error", {"code": "40000", "message": "所选知识库无效或无权限"})
                return

            session = await session_service.get_or_create_session(
                db, payload.session_id, user, [str(x) for x in accessible]
            )
            _emit(queue, "message_start", {"session_id": str(session.id)})

            await session_service.append_message(
                db, session.id, "user", payload.message
            )
            recent = await session_service.get_recent_messages(db, session.id)
            messages = [{"role": m.role, "content": m.content} for m in recent]
            if payload.form_data:
                # 对话内表单：提交内容作为上下文注入（03 §4.5）
                form_text = "；".join(
                    f"{k}={v}" for k, v in payload.form_data.items() if v
                )
                if messages:
                    messages[-1] = {
                        **messages[-1],
                        "content": messages[-1]["content"] + f"\n[表单已提交：{form_text}]",
                    }

            profile = None
            if payload.model_profile_id:
                profile = await model_profile_service.get_profile(
                    db, payload.model_profile_id
                )
            else:
                profile = await model_profile_service.get_default_profile(db)

            state: ChatState = {
                "session_id": str(session.id),
                "user_id": str(user.id),
                "messages": messages,
                "kb_ids": [str(x) for x in accessible],
                "escalation_count": session.escalation_count,
                "form_data": payload.form_data,
                "model_profile_id": (
                    str(payload.model_profile_id) if payload.model_profile_id else None
                ),
                "queue": queue,
                "trace": [],
                "citations": [],
                "answer": "",
            }
            if profile:
                state["model_name"] = profile.model

            started = time.perf_counter()
            result = await chat_graph.ainvoke(state)

            assistant = await session_service.append_message(
                db,
                session.id,
                "assistant",
                result.get("answer", ""),
                intent=result.get("intent"),
                cited_chunk_ids=[
                    str(c["chunk_id"]) for c in result.get("citations", [])
                ],
            )

            ticket_no = None
            if result.get("ticket"):
                ticket_no = result["ticket"]["ticket_no"]
                await session_service.append_message(
                    db,
                    session.id,
                    "system",
                    f"已为您转接人工客服，工单号 {ticket_no}，请稍候",
                )
                session.status = "transferred"

            session.escalation_count = result.get(
                "escalation_count", session.escalation_count
            )
            await db.commit()

            latency_ms = int((time.perf_counter() - started) * 1000)
            await session_service.save_trace(
                db,
                session.id,
                request_id=request_id,
                steps=result.get("trace", []),
                latency_ms=latency_ms,
                message_id=assistant.id,
            )

            # 精简字段 + UUID 转字符串后下发（JSON 序列化）
            _CITATION_FIELDS = (
                "chunk_id",
                "kb_id",
                "document_name",
                "page",
                "row",
                "question",
                "answer",
                "retrieval_score",
                "rerank_score",
            )
            citations = [
                {
                    field: str(c[field]) if field in ("chunk_id", "kb_id") else c.get(field)
                    for field in _CITATION_FIELDS
                }
                for c in result.get("citations", [])
            ]
            _emit(queue, "citations", {"citations": citations})
            _emit(
                queue,
                "done",
                {
                    "message_id": str(assistant.id),
                    "intent": result.get("intent"),
                    "ticket_no": ticket_no,
                    "session_id": str(session.id),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat_pipeline_error", request_id=request_id)
            code = getattr(exc, "code", 50000)
            message = getattr(exc, "message", "服务内部错误，请稍后重试")
            _emit(queue, "error", {"code": str(code), "message": message})


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
) -> StreamingResponse:
    """SSE 流式对话（08 §4.4 协议：message_start / token / citations / done / error）。"""
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_run_chat_pipeline(payload, user, queue))

    async def event_stream():
        try:
            while True:
                item = await queue.get()
                yield sse(item["event"], item["data"])
                if item["event"] in ("done", "error"):
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions", response_model=ResponseModel[PageData[SessionOut]])
async def list_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await session_service.list_sessions(db, page, page_size)
    return ok(
        data=PageData[SessionOut](
            items=[SessionOut.model_validate(s) for s in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/sessions/{session_id}", response_model=ResponseModel[SessionDetailOut])
async def get_session(
    session_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    session, messages = await session_service.get_session_with_messages(db, session_id)
    return ok(
        data=SessionDetailOut(
            session=SessionOut.model_validate(session),
            messages=[MessageOut.model_validate(m) for m in messages],
        )
    )
