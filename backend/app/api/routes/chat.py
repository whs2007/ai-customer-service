"""智能客服对话接口（08 §4.4 / 03）：SSE 流式对话（管理端/客服端）。"""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import require_roles
from app.core.ratelimit import enforce_chat_rate_limit
from app.models.user import Role, User
from app.schemas.chat import ChatRequest
from app.services.chat_pipeline import run_chat_pipeline

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
) -> StreamingResponse:
    """SSE 流式对话（08 §4.4 协议：message_start / token / citations / done / error）。"""
    await enforce_chat_rate_limit(user)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        run_chat_pipeline(
            session_id=payload.session_id,
            message=payload.message,
            user=user,
            queue=queue,
            kb_ids=payload.kb_ids,
            model_profile_id=payload.model_profile_id,
            form_data=payload.form_data,
            channel="web",
        )
    )

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
