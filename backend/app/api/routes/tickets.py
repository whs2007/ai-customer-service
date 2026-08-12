"""客服工单接口（06 / 08 §6.2）。"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.services import ticket_service
from app.services.audit_service import write_audit

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketAction(BaseModel):
    action: str = Field(pattern="^(start|close)$", description="start 开始处理 / close 关闭")
    note: str = Field(default="", max_length=500, description="备注/处理结果")


def _parse_date(value: date) -> datetime:
    """日期 → 当日 00:00（UTC，按 Asia/Shanghai 零点折算）。"""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Shanghai")
    local = datetime.combine(value, time.min, tzinfo=tz)
    return local.astimezone(timezone.utc)


@router.get("", response_model=ResponseModel[PageData[dict]])
async def list_tickets(
    status: str | None = Query(default=None, description="open/processing/closed"),
    priority: str | None = Query(default=None, description="high/medium/low"),
    start_date: date | None = Query(default=None, description="创建时间起"),
    end_date: date | None = Query(default=None, description="创建时间止"),
    keyword: str | None = Query(default=None, max_length=100, description="编号/内容关键词"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await ticket_service.list_tickets(
        db,
        status=status,
        priority=priority,
        start_date=_parse_date(start_date) if start_date else None,
        end_date=(
            datetime.combine(end_date, time.max, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Shanghai"))
            .astimezone(timezone.utc)
            if end_date
            else None
        ),
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    data = [
        {
            "id": str(t.id),
            "ticket_no": t.ticket_no,
            "session_id": str(t.session_id),
            "type": t.type,
            "content": t.content,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in items
    ]
    return ok(
        data=PageData[dict](items=data, total=total, page=page, page_size=page_size)
    )


@router.get("/{ticket_id}", response_model=ResponseModel)
async def get_ticket(
    ticket_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await ticket_service.get_ticket_detail(db, ticket_id))


@router.post("/{ticket_id}/action", response_model=ResponseModel)
async def ticket_action(
    ticket_id: uuid.UUID,
    payload: TicketAction,
    request: Request,
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    ticket = await ticket_service.transition_ticket(
        db, ticket_id, payload.action, payload.note, user
    )
    await write_audit(
        db,
        action=f"ticket_{payload.action}",
        user_id=str(user.id),
        ip=request.client.host if request.client else None,
        target_type="ticket",
        target_id=str(ticket_id),
        detail={"ticket_no": ticket.ticket_no, "status": ticket.status, "note": payload.note[:200]},
    )
    return ok(
        data={
            "id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
        },
        message="操作成功",
    )

