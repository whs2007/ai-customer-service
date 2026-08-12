"""工单服务（06 / 08 §4.5）：列表筛选、详情（命中片段+时间线）、状态流转。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.ticket import Ticket
from app.models.ticket_note import TicketNote
from app.models.user import User
from app.services import chunk_service

# 状态机：open → processing → closed（禁止跳级/回退，08 §4.5）
TRANSITIONS: dict[str, tuple[str, str]] = {
    "start": ("open", "processing"),
    "close": ("processing", "closed"),
}


async def list_tickets(
    db: AsyncSession,
    *,
    status: str | None = None,
    priority: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Ticket], int]:
    stmt = select(Ticket)
    count_stmt = select(func.count()).select_from(Ticket)
    if status:
        stmt = stmt.where(Ticket.status == status)
        count_stmt = count_stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
        count_stmt = count_stmt.where(Ticket.priority == priority)
    if start_date is not None:
        stmt = stmt.where(Ticket.created_at >= start_date)
        count_stmt = count_stmt.where(Ticket.created_at >= start_date)
    if end_date is not None:
        stmt = stmt.where(Ticket.created_at <= end_date)
        count_stmt = count_stmt.where(Ticket.created_at <= end_date)
    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(or_(Ticket.ticket_no.ilike(kw), Ticket.content.ilike(kw)))
        count_stmt = count_stmt.where(
            or_(Ticket.ticket_no.ilike(kw), Ticket.content.ilike(kw))
        )
    total = await db.scalar(count_stmt) or 0
    result = await db.execute(
        stmt.order_by(Ticket.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError("工单不存在")
    return ticket


async def get_ticket_detail(db: AsyncSession, ticket_id: uuid.UUID) -> dict:
    """工单详情：基础信息 + 命中片段明细 + 处理记录时间线（含操作人）。"""
    ticket = await get_ticket(db, ticket_id)
    notes_rows = (
        await db.execute(
            select(TicketNote, User.display_name)
            .outerjoin(User, User.id == TicketNote.operator_id)
            .where(TicketNote.ticket_id == ticket_id)
            .order_by(TicketNote.created_at)
        )
    ).all()
    notes = [
        {
            "id": str(n.id),
            "note": n.note,
            "status_from": n.status_from,
            "status_to": n.status_to,
            "operator": display_name or "",
            "created_at": n.created_at,
        }
        for n, display_name in notes_rows
    ]
    cited_ids = [uuid.UUID(str(x)) for x in (ticket.cited_chunk_ids or [])]
    citation_map = await chunk_service.get_citations_by_chunk_ids(db, cited_ids)
    citations = [
        {
            key: (str(value) if key in ("chunk_id", "kb_id") else value)
            for key, value in citation_map[cid].items()
        }
        for cid in cited_ids
        if cid in citation_map
    ]
    return {
        "id": str(ticket.id),
        "ticket_no": ticket.ticket_no,
        "session_id": str(ticket.session_id),
        "type": ticket.type,
        "content": ticket.content,
        "status": ticket.status,
        "priority": ticket.priority,
        "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "citations": citations,
        "notes": notes,
    }


async def transition_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    action: str,
    note: str,
    user: User,
) -> Ticket:
    """状态流转：open→processing（start）/ processing→closed（close），写 ticket_notes。"""
    if action not in TRANSITIONS:
        raise BadRequestError("不支持的操作（支持 start / close）")
    status_from, status_to = TRANSITIONS[action]
    ticket = await get_ticket(db, ticket_id)
    if ticket.status != status_from:
        raise BadRequestError(
            f"状态流转不合法：当前 {ticket.status}，需为 {status_from} 才能执行 {action}"
        )
    ticket.status = status_to
    if action == "start":
        ticket.assignee_id = user.id
    db.add(
        TicketNote(
            ticket_id=ticket_id,
            operator_id=user.id,
            note=note or "",
            status_from=status_from,
            status_to=status_to,
        )
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket

