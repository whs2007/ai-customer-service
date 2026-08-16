"""客服工作台接口（13 / 开发文档 01 §5）：队列、原子认领、回复、关闭、在线、已读。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles, require_ticket_operator
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.response import PageData, ResponseModel, ok
from app.models.session import ChatSession
from app.models.ticket import Ticket
from app.models.user import Role, User
from app.services import agent_service, read_service, ticket_service
from app.services.audit_service import write_audit

router = APIRouter(prefix="/agent", tags=["agent"])


class ReplyRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000, description="客服回复内容")


class CloseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=200, description="关闭原因（必填）")


class ReleaseRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200, description="释放原因（可选）")


class ReadRequest(BaseModel):
    last_read_message_id: uuid.UUID | None = Field(default=None)


class OnlineRequest(BaseModel):
    online: bool


@router.get("/tickets", response_model=ResponseModel[PageData[dict]])
async def agent_tickets(
    status: str = Query(default="all", pattern="^(all|open|processing|closed)$"),
    mine: bool = Query(default=False, description="只看我负责的"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(require_roles(Role.AGENT, Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await ticket_service.list_agent_tickets(
        db, user, status=status, mine=mine, page=page, page_size=page_size
    )
    return ok(
        data=PageData[dict](items=items, total=total, page=page, page_size=page_size)
    )


@router.post("/tickets/{ticket_id}/claim", response_model=ResponseModel)
async def claim_ticket(
    ticket_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_ticket_operator()),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """原子认领：仅 open 状态可认领，冲突返回 40900。"""
    ticket = await ticket_service.claim_ticket(db, ticket_id, user)
    await write_audit(
        db,
        action="ticket_claim",
        user_id=str(user.id),
        ip=request.client.host if request.client else None,
        target_type="ticket",
        target_id=str(ticket.id),
        detail={"ticket_no": ticket.ticket_no, "status": ticket.status},
    )
    await db.commit()
    return ok(
        data={
            "id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
            "claimed_at": ticket.claimed_at,
        },
        message="认领成功",
    )


@router.get("/tickets/{ticket_id}", response_model=ResponseModel)
async def agent_ticket_detail(
    ticket_id: uuid.UUID,
    user: User = Depends(require_roles(Role.AGENT, Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await ticket_service.get_agent_ticket_detail(db, ticket_id, user))


@router.post("/tickets/{ticket_id}/reply", response_model=ResponseModel)
async def reply_ticket(
    ticket_id: uuid.UUID,
    payload: ReplyRequest,
    request: Request,
    user: User = Depends(require_ticket_operator()),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    message = await ticket_service.reply_ticket(db, ticket_id, user, payload.content)
    await write_audit(
        db,
        action="ticket_reply",
        user_id=str(user.id),
        ip=request.client.host if request.client else None,
        target_type="ticket",
        target_id=str(ticket_id),
        detail={"ticket_no": None, "content_length": len(payload.content)},
    )
    await db.commit()
    return ok(
        data={
            "id": str(message.id),
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
        },
        message="回复成功",
    )


@router.post("/tickets/{ticket_id}/close", response_model=ResponseModel)
async def close_ticket(
    ticket_id: uuid.UUID,
    payload: CloseRequest,
    request: Request,
    user: User = Depends(require_ticket_operator()),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    ticket = await ticket_service.close_ticket(db, ticket_id, user, payload.reason)
    await write_audit(
        db,
        action="ticket_close",
        user_id=str(user.id),
        ip=request.client.host if request.client else None,
        target_type="ticket",
        target_id=str(ticket.id),
        detail={"ticket_no": ticket.ticket_no, "reason": ticket.close_reason},
    )
    await db.commit()
    return ok(
        data={
            "id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
            "closed_at": ticket.closed_at,
        },
        message="工单已关闭",
    )


@router.post("/tickets/{ticket_id}/release", response_model=ResponseModel)
async def release_ticket(
    ticket_id: uuid.UUID,
    payload: ReleaseRequest,
    request: Request,
    user: User = Depends(require_ticket_operator()),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """释放工单（assignee/admin）：处理中 → 待处理，其他客服可重新认领。"""
    ticket = await ticket_service.release_ticket(
        db, ticket_id, user, payload.reason or ""
    )
    await write_audit(
        db,
        action="ticket_release",
        user_id=str(user.id),
        ip=request.client.host if request.client else None,
        target_type="ticket",
        target_id=str(ticket.id),
        detail={"ticket_no": ticket.ticket_no, "status": ticket.status},
    )
    await db.commit()
    return ok(
        data={
            "id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
        },
        message="工单已释放回待处理",
    )


@router.put("/status", response_model=ResponseModel)
async def set_status(
    payload: OnlineRequest,
    user: User = Depends(require_ticket_operator()),
) -> ResponseModel:
    await agent_service.set_online(str(user.id), payload.online)
    return ok(data={"online": payload.online}, message="状态已更新")


@router.get("/status", response_model=ResponseModel)
async def get_status(
    user: User = Depends(require_ticket_operator()),
) -> ResponseModel:
    return ok(data={"online": await agent_service.is_online(str(user.id))})


@router.post("/sessions/{session_id}/read", response_model=ResponseModel)
async def mark_session_read(
    session_id: uuid.UUID,
    payload: ReadRequest,
    user: User = Depends(require_ticket_operator()),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    # 【修复 M5】归属校验：会话需存在，且其工单为 open 或归当前客服/admin 负责
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise NotFoundError("会话不存在")
    if user.role != "admin":
        ticket = await db.scalar(
            select(Ticket)
            .where(Ticket.session_id == session_id)
            .order_by(Ticket.created_at.desc())
            .limit(1)
        )
        if ticket is None or (
            ticket.status != "open"
            and (ticket.assignee_id is None or ticket.assignee_id != user.id)
        ):
            raise ForbiddenError("无权操作该会话")
    await read_service.upsert_read_cursor(
        db, session_id, "agent", user.id, payload.last_read_message_id
    )
    return ok(data={"ok": True})
