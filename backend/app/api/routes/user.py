"""用户端接口（12 / 开发文档 01 §3）：对话 SSE、会话、工单、已读、评价。

权限：仅 user 角色；所有查询行级归属校验（越权 403）；响应字段最小化。
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.ratelimit import enforce_chat_rate_limit
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.services import user_service
from app.services.chat_pipeline import run_chat_pipeline

router = APIRouter(prefix="/user", tags=["user"])


class UserChatRequest(BaseModel):
    """用户端对话请求：不接收 kb_ids/model_profile_id/form_data（后端按渠道解析）。"""

    session_id: uuid.UUID | None = Field(default=None, description="为空则新建/恢复会话")
    message: str = Field(min_length=1, max_length=500, description="用户消息")


class UserReadRequest(BaseModel):
    last_read_message_id: uuid.UUID | None = Field(default=None, description="已读到的消息 ID")


class UserRatingRequest(BaseModel):
    """工单评价（P2 接口预留，12 §4.4）。"""

    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def user_chat(
    payload: UserChatRequest,
    user: User = Depends(require_roles(Role.USER)),
) -> StreamingResponse:
    """用户端 SSE 流式对话（开发文档 01 §3.1）：kb_ids 由渠道配置解析，引用脱敏。"""
    await enforce_chat_rate_limit(user)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        run_chat_pipeline(
            session_id=payload.session_id,
            message=payload.message,
            user=user,
            queue=queue,
            kb_ids=None,
            sanitize_citations=True,
            channel="web_user",
        )
    )

    async def event_stream():
        try:
            while True:
                item = await queue.get()
                yield _sse(item["event"], item["data"])
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


@router.get("/sessions", response_model=ResponseModel[PageData[dict]])
async def my_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user: User = Depends(require_roles(Role.USER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await user_service.list_my_sessions(db, user, page, page_size)
    return ok(
        data=PageData[dict](items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/sessions/{session_id}", response_model=ResponseModel)
async def my_session(
    session_id: uuid.UUID,
    user: User = Depends(require_roles(Role.USER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await user_service.get_my_session(db, user, session_id))


@router.post("/sessions/{session_id}/read", response_model=ResponseModel)
async def my_session_read(
    session_id: uuid.UUID,
    payload: UserReadRequest,
    user: User = Depends(require_roles(Role.USER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(
        data=await user_service.mark_my_session_read(
            db, user, session_id, payload.last_read_message_id
        )
    )


@router.get("/tickets", response_model=ResponseModel[PageData[dict]])
async def my_tickets(
    status: str | None = Query(default=None, pattern="^(open|processing|closed)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user: User = Depends(require_roles(Role.USER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await user_service.list_my_tickets(
        db, user, status, page, page_size
    )
    return ok(
        data=PageData[dict](items=items, total=total, page=page, page_size=page_size)
    )


@router.get("/tickets/{ticket_id}", response_model=ResponseModel)
async def my_ticket(
    ticket_id: uuid.UUID,
    user: User = Depends(require_roles(Role.USER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await user_service.get_my_ticket(db, user, ticket_id))


@router.post("/tickets/{ticket_id}/rating", response_model=ResponseModel)
async def rate_ticket(
    ticket_id: uuid.UUID,
    payload: UserRatingRequest,
    user: User = Depends(require_roles(Role.USER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """工单满意度评价（P2 接口预留；11 §4.4 一张工单只能评一次）。"""
    rating = await user_service.rate_my_ticket(
        db, user, ticket_id, payload.score, payload.comment
    )
    return ok(
        data={"id": str(rating.id), "score": rating.score, "comment": rating.comment},
        message="评价已提交",
    )
