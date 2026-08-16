"""工单服务（06 / 08 §4.5 + 13 客服工作台）：列表/详情/状态流转/认领/回复/关闭。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.message import Message
from app.models.ticket import Ticket
from app.models.ticket_note import TicketNote
from app.models.ticket_rating import TicketRating
from app.models.user import User
from app.services import chunk_service, read_service, session_service
from app.services.event_service import publish_event

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
    """状态流转：open→processing（start）/ processing→closed（close），写 ticket_notes。

    与工作台 claim/close 保持字段一致：start 写 claimed_at，close 写 closed_at/close_reason，
    并发布对应 SSE 事件（保证管理端/工作台/用户端三端实时同步）。
    """
    if action not in TRANSITIONS:
        raise BadRequestError("不支持的操作（支持 start / close）")
    status_from, status_to = TRANSITIONS[action]
    ticket = await get_ticket(db, ticket_id)
    if ticket.status != status_from:
        raise BadRequestError(
            f"状态流转不合法：当前 {ticket.status}，需为 {status_from} 才能执行 {action}"
        )
    ticket.status = status_to
    now = datetime.now(UTC)
    if action == "start":
        ticket.assignee_id = user.id
        ticket.claimed_at = now
    elif action == "close":
        ticket.closed_at = now
        reason = note.strip()
        ticket.close_reason = reason[:200] if reason else None
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
    if action == "start":
        publish_event(
            "ticket.claimed",
            {
                "ticket_id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "session_id": str(ticket.session_id),
                "user_id": str(ticket.user_id) if ticket.user_id else None,
                "assignee_id": str(user.id),
                "ticket_status": ticket.status,
                "claimed_at": ticket.claimed_at.isoformat() if ticket.claimed_at else None,
            },
        )
    elif action == "close":
        publish_event(
            "ticket.closed",
            {
                "ticket_id": str(ticket.id),
                "ticket_no": ticket.ticket_no,
                "session_id": str(ticket.session_id),
                "user_id": str(ticket.user_id) if ticket.user_id else None,
                "ticket_status": ticket.status,
                "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
                "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
                "reason": ticket.close_reason,
            },
        )
    return ticket


async def _can_handle_ticket(db: AsyncSession, ticket_id: uuid.UUID, user: User) -> Ticket:
    """回复/关闭/释放权限：assignee；admin 仅在 allow_admin_ticket_ops=true 时允许（职责分离）。"""
    ticket = await get_ticket(db, ticket_id)
    if user.role == "admin":
        if get_settings().allow_admin_ticket_ops:
            return ticket
        raise ForbiddenError("管理员不处理工单，请使用客服账号")
    if ticket.assignee_id is None or ticket.assignee_id != user.id:
        raise ForbiddenError("仅工单负责人或管理员可操作")
    return ticket


async def claim_ticket(db: AsyncSession, ticket_id: uuid.UUID, user: User) -> Ticket:
    """原子认领（开发文档 01 §5.2 / 13 §2.3）：
    单条条件 UPDATE，WHERE status='open'，rowcount=0 视为已被他人认领。
    """
    result = await db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "open")
        .values(
            assignee_id=user.id,
            status="processing",
            claimed_at=datetime.now(UTC),
        )
        .returning(Ticket.id)
    )
    claimed_id = result.scalar_one_or_none()
    if claimed_id is None:
        raise ConflictError("该工单已被其他客服认领")
    db.add(
        TicketNote(
            ticket_id=ticket_id,
            operator_id=user.id,
            note="客服认领工单",
            status_from="open",
            status_to="processing",
        )
    )
    await db.commit()
    ticket = await get_ticket(db, ticket_id)
    publish_event(
        "ticket.claimed",
        {
            "ticket_id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "session_id": str(ticket.session_id),
            "user_id": str(ticket.user_id) if ticket.user_id else None,
            "assignee_id": str(user.id),
            "ticket_status": ticket.status,
            "claimed_at": ticket.claimed_at.isoformat() if ticket.claimed_at else None,
        },
    )
    return ticket


async def reply_ticket(
    db: AsyncSession, ticket_id: uuid.UUID, user: User, content: str
) -> Message:
    """人工客服回复（开发文档 01 §5.4）：写入 role='agent' 消息，发布 message.new。"""
    ticket = await _can_handle_ticket(db, ticket_id, user)
    if ticket.status == "closed":
        raise BadRequestError("工单已关闭，不能回复")
    message = await session_service.append_message(
        db, ticket.session_id, "agent", content.strip()[:2000]
    )
    publish_event(
        "message.new",
        {
            "message_id": str(message.id),
            "session_id": str(ticket.session_id),
            "ticket_id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "user_id": str(ticket.user_id) if ticket.user_id else None,
            "ticket_status": ticket.status,
            "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            "role": "agent",
            "created_at": message.created_at.isoformat(),
            "from_agent": str(user.id),
        },
    )
    return message


async def close_ticket(
    db: AsyncSession, ticket_id: uuid.UUID, user: User, reason: str
) -> Ticket:
    """关闭工单（13 §2.2）：仅处理中可关闭，关闭原因必填。"""
    ticket = await _can_handle_ticket(db, ticket_id, user)
    if ticket.status != "processing":
        raise BadRequestError("仅处理中的工单可关闭")
    ticket.status = "closed"
    ticket.closed_at = datetime.now(UTC)
    ticket.close_reason = reason.strip()[:200]
    db.add(
        TicketNote(
            ticket_id=ticket_id,
            operator_id=user.id,
            note=f"关闭工单：{ticket.close_reason}",
            status_from="processing",
            status_to="closed",
        )
    )
    await db.commit()
    await db.refresh(ticket)
    publish_event(
        "ticket.closed",
        {
            "ticket_id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "session_id": str(ticket.session_id),
            "user_id": str(ticket.user_id) if ticket.user_id else None,
            "ticket_status": ticket.status,
            "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
            "reason": ticket.close_reason,
        },
    )
    return ticket


async def release_ticket(
    db: AsyncSession, ticket_id: uuid.UUID, user: User, reason: str = ""
) -> Ticket:
    """释放工单（assignee/admin）：processing → open，清空 assignee/claimed_at。

    用于误认领/转派前置操作：释放后回到待处理队列，任何客服可重新认领。
    条件更新防止与关闭等操作并发竞态；写 ticket_notes 并发布 ticket.updated 事件。
    """
    ticket = await _can_handle_ticket(db, ticket_id, user)
    if ticket.status != "processing":
        raise BadRequestError("仅处理中的工单可释放")
    result = await db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "processing")
        .values(assignee_id=None, status="open", claimed_at=None)
        .returning(Ticket.id)
    )
    if result.scalar_one_or_none() is None:
        raise ConflictError("工单状态已变化，请刷新后重试")
    note = reason.strip()
    db.add(
        TicketNote(
            ticket_id=ticket_id,
            operator_id=user.id,
            note=f"释放工单：{note}" if note else "释放工单",
            status_from="processing",
            status_to="open",
        )
    )
    await db.commit()
    ticket = await get_ticket(db, ticket_id)
    publish_event(
        "ticket.updated",
        {
            "ticket_id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "session_id": str(ticket.session_id),
            "user_id": str(ticket.user_id) if ticket.user_id else None,
            "ticket_status": ticket.status,
            "assignee_id": None,
            "priority": ticket.priority,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    return ticket


async def list_agent_tickets(
    db: AsyncSession,
    user: User,
    *,
    status: str = "all",
    mine: bool = False,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[dict], int]:
    """客服工作台队列（开发文档 01 §5.1）：open 按优先级+创建时间，processing 按认领时间。"""
    stmt = select(Ticket)
    count_stmt = select(func.count()).select_from(Ticket)
    if status in ("open", "processing", "closed"):
        stmt = stmt.where(Ticket.status == status)
        count_stmt = count_stmt.where(Ticket.status == status)
    if mine:
        stmt = stmt.where(Ticket.assignee_id == user.id)
        count_stmt = count_stmt.where(Ticket.assignee_id == user.id)
    # 【修复】列表与详情权限对齐（11 §10.1：客服端只能访问待处理或自己负责的工单）：
    # 非 admin 仅能看到 open 全部 + 自己负责的 processing/closed；admin 全量。
    if user.role != "admin" and not mine:
        if status in ("processing", "closed"):
            stmt = stmt.where(Ticket.assignee_id == user.id)
            count_stmt = count_stmt.where(Ticket.assignee_id == user.id)
        elif status == "all":
            own_or_open = or_(Ticket.status == "open", Ticket.assignee_id == user.id)
            stmt = stmt.where(own_or_open)
            count_stmt = count_stmt.where(own_or_open)

    priority_order = case(
        (Ticket.priority == "high", 0),
        (Ticket.priority == "medium", 1),
        else_=2,
    )
    order = (
        priority_order.asc(), Ticket.created_at.asc()
        if status == "open"
        else Ticket.claimed_at.desc()
    )
    stmt = stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)
    total = await db.scalar(count_stmt) or 0
    tickets = list((await db.execute(stmt)).scalars().all())
    if not tickets:
        return [], total
    return await _enrich_agent_tickets(db, tickets, user), total


async def _enrich_agent_tickets(
    db: AsyncSession, tickets: list[Ticket], user: User
) -> list[dict]:
    session_ids = [t.session_id for t in tickets]
    user_ids = [t.user_id for t in tickets if t.user_id]

    name_map: dict[uuid.UUID, str] = {}
    if user_ids:
        rows = await db.execute(
            select(User.id, User.display_name).where(User.id.in_(user_ids))
        )
        name_map = {uid: name for uid, name in rows.all()}

    # 【P1-3】last_message 用 DISTINCT ON 只取每会话最新一条，避免全量拉取
    last_map: dict[uuid.UUID, tuple[str, datetime]] = {}
    if session_ids:
        rows = await db.execute(
            select(Message.session_id, Message.content, Message.created_at)
            .where(Message.session_id.in_(session_ids))
            .distinct(Message.session_id)
            .order_by(Message.session_id, Message.created_at.desc(), Message.id.desc())
        )
        last_map = {
            sid: (content, created_at) for sid, content, created_at in rows.all()
        }

    # 【P1-3】未读数批量聚合：单条 SQL 一次算完，避免每工单 N+1 次查询
    unread_map: dict[uuid.UUID, int] = await read_service.get_unread_counts(
        db, session_ids, "agent", user.id
    )

    items = []
    for t in tickets:
        last = last_map.get(t.session_id)
        items.append(
            {
                "id": str(t.id),
                "ticket_no": t.ticket_no,
                "status": t.status,
                "priority": t.priority,
                "user_id": str(t.user_id) if t.user_id else None,
                "user_name": name_map.get(t.user_id, "") if t.user_id else "",
                "session_id": str(t.session_id),
                "unread_count": unread_map.get(t.session_id, 0),
                "last_message": last[0] if last else "",
                "last_message_at": last[1] if last else None,
                "claimed_at": t.claimed_at,
                "closed_at": t.closed_at,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
        )
    return items


async def get_agent_ticket_detail(
    db: AsyncSession, ticket_id: uuid.UUID, user: User
) -> dict:
    """客服端工单详情：完整内部字段 + 用户资料 + 评分 + 未读数。"""
    ticket = await get_ticket(db, ticket_id)
    if not (
        user.role == "admin"
        or ticket.status == "open"
        or (ticket.assignee_id is not None and ticket.assignee_id == user.id)
    ):
        raise ForbiddenError("无权查看该工单")
    messages = (
        await db.execute(
            select(Message)
            .where(Message.session_id == ticket.session_id)
            .order_by(Message.created_at, Message.id)
        )
    ).scalars().all()
    user_row = await db.get(User, ticket.user_id) if ticket.user_id else None
    rating = await db.scalar(
        select(TicketRating).where(TicketRating.ticket_id == ticket_id)
    )
    unread = await read_service.get_unread_count(
        db, ticket.session_id, "agent", user.id
    )
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
    # 【P1-3】详情引用一次反查：收集全部 chunk id 后单次查询，再按消息映射
    msg_out: list[dict[str, Any]] = []
    cited_by_msg: dict[uuid.UUID, list[uuid.UUID]] = {}
    for m in messages:
        if m.cited_chunk_ids:
            cited_by_msg[m.id] = [uuid.UUID(str(x)) for x in m.cited_chunk_ids]
    all_cited = [cid for ids in cited_by_msg.values() for cid in ids]
    citation_map = (
        await chunk_service.get_citations_by_chunk_ids(db, all_cited) if all_cited else {}
    )
    for m in messages:
        item: dict[str, Any] = {
            "id": str(m.id),
            "session_id": str(m.session_id),
            "role": m.role,
            "content": m.content,
            "intent": m.intent,
            "cited_chunk_ids": [str(x) for x in (m.cited_chunk_ids or [])],
            "created_at": m.created_at,
        }
        cited = cited_by_msg.get(m.id, [])
        if cited:
            item["citations"] = [
                {
                    key: (str(value) if key in ("chunk_id", "kb_id") else value)
                    for key, value in citation_map[cid].items()
                }
                for cid in cited
                if cid in citation_map
            ]
        msg_out.append(item)
    return {
        "ticket": {
            "id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "session_id": str(ticket.session_id),
            "type": ticket.type,
            "content": ticket.content,
            "status": ticket.status,
            "priority": ticket.priority,
            "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            "claimed_at": ticket.claimed_at,
            "closed_at": ticket.closed_at,
            "close_reason": ticket.close_reason,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
        },
        "user": (
            {
                "id": str(user_row.id),
                "username": user_row.username,
                "display_name": user_row.display_name,
            }
            if user_row
            else None
        ),
        "messages": msg_out,
        "rating": {"score": rating.score, "comment": rating.comment} if rating else None,
        "unread_count": unread,
        "notes": notes,
    }
