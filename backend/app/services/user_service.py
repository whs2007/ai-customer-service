"""用户管理服务（B6a：账号权限 Tab）。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models.message import Message
from app.models.session import ChatSession
from app.models.ticket import Ticket
from app.models.ticket_rating import TicketRating
from app.models.user import User
from app.schemas.auth import UserCreate, UserUpdate
from app.services import read_service
from app.services.token_security import revoke_all_user_tokens


async def list_users(
    db: AsyncSession, page: int, page_size: int
) -> tuple[list[User], int]:
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    existing = await db.scalar(select(User).where(User.username == payload.username.strip()))
    if existing is not None:
        raise ConflictError("用户名已存在")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role=payload.role.value,
        status=payload.status.value,
    )
    db.add(user)
    try:
        # 【修复 M3】并发建号同名：唯一约束冲突转 409，而不是 500
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise ConflictError("用户名已存在") from None
    return user


async def update_user(
    db: AsyncSession, user_id: uuid.UUID | str, payload: UserUpdate
) -> User:
    user_id = uuid.UUID(str(user_id))
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    role_changed = payload.role is not None and payload.role.value != user.role
    status_changed = payload.status is not None and payload.status.value != user.status
    if payload.role is not None:
        user.role = payload.role.value
    if payload.status is not None:
        user.status = payload.status.value
    if role_changed or status_changed:
        # 角色/状态变更 = 会话状态变更：旧 token（含旧角色声明）立即失效
        await revoke_all_user_tokens(db, user.id)
    await db.commit()
    await db.refresh(user)
    return user


async def reset_password(
    db: AsyncSession, user_id: uuid.UUID | str, new_password: str
) -> User:
    user_id = uuid.UUID(str(user_id))
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    user.password_hash = hash_password(new_password)
    # 改密后旧会话立即失效（access 与 refresh 全部作废）
    await revoke_all_user_tokens(db, user.id)
    await db.commit()
    await db.refresh(user)
    return user


def _ensure_owned(session: ChatSession, user: User) -> None:
    """行级权限：用户端只能访问自己的会话（越权 403，开发文档 01 §3）。"""
    if session.user_id is None or session.user_id != user.id:
        raise ForbiddenError("无权访问该会话")


async def list_my_sessions(
    db: AsyncSession, user: User, page: int, page_size: int
) -> tuple[list[dict], int]:
    """用户端会话列表（12 §3.2）：最近更新排序，active 置顶。"""
    base = select(ChatSession).where(ChatSession.user_id == user.id)
    total = await db.scalar(
        select(func.count()).select_from(ChatSession).where(ChatSession.user_id == user.id)
    ) or 0
    result = await db.execute(
        base.order_by(
            (ChatSession.status == "active").desc(), ChatSession.updated_at.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    sessions = list(result.scalars().all())
    if not sessions:
        return [], total
    ids = [s.id for s in sessions]
    counts: dict[uuid.UUID, int] = {
        sid: count
        for sid, count in (
            await db.execute(
                select(Message.session_id, func.count(Message.id))
                .where(Message.session_id.in_(ids))
                .group_by(Message.session_id)
            )
        ).all()
    }
    last_messages: dict[uuid.UUID, str] = {}
    for sid, content in (
        await db.execute(
            select(Message.session_id, Message.content)
            .where(Message.session_id.in_(ids))
            .order_by(Message.created_at.desc(), Message.id.desc())
        )
    ).all():
        last_messages.setdefault(sid, content)
    ticket_map: dict[uuid.UUID, str] = {}
    for sid, no in (
        await db.execute(
            select(Ticket.session_id, Ticket.ticket_no)
            .where(Ticket.session_id.in_(ids))
            .order_by(Ticket.created_at.desc())
        )
    ).all():
        ticket_map.setdefault(sid, no)
    items = [
        {
            "id": str(s.id),
            "status": s.status,
            "updated_at": s.updated_at,
            "message_count": counts.get(s.id, 0),
            "last_message": last_messages.get(s.id, ""),
            "ticket_no": ticket_map.get(s.id),
        }
        for s in sessions
    ]
    return items, total


async def get_my_session(
    db: AsyncSession, user: User, session_id: uuid.UUID
) -> dict:
    """用户端会话详情：归属校验 + 消息脱敏（无 intent/cited_chunk_ids/trace）。"""
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise NotFoundError("会话不存在")
    _ensure_owned(session, user)
    messages = (
        await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at, Message.id)
        )
    ).scalars().all()
    return {
        "session": {
            "id": str(session.id),
            "status": session.status,
            "channel": session.channel,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        },
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


async def _get_owned_ticket(
    db: AsyncSession, user: User, ticket_id: uuid.UUID
) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError("工单不存在")
    if ticket.user_id is None or ticket.user_id != user.id:
        raise ForbiddenError("无权访问该工单")
    return ticket


async def list_my_tickets(
    db: AsyncSession,
    user: User,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict], int]:
    """用户端我的工单（12 §4.1）：仅本人工单。"""
    base = select(Ticket).where(Ticket.user_id == user.id)
    count_base = select(func.count()).select_from(Ticket).where(
        Ticket.user_id == user.id
    )
    if status:
        base = base.where(Ticket.status == status)
        count_base = count_base.where(Ticket.status == status)
    total = await db.scalar(count_base) or 0
    result = await db.execute(
        base.order_by(Ticket.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    tickets = list(result.scalars().all())
    items = [
        {
            "id": str(t.id),
            "ticket_no": t.ticket_no,
            "status": t.status,
            "priority": t.priority,
            "session_id": str(t.session_id),
            "claimed_at": t.claimed_at,
            "closed_at": t.closed_at,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in tickets
    ]
    return items, total


async def get_my_ticket(
    db: AsyncSession, user: User, ticket_id: uuid.UUID
) -> dict:
    """用户端工单详情：工单 + 会话消息（脱敏）+ 评价状态（12 §4.2）。"""
    ticket = await _get_owned_ticket(db, user, ticket_id)
    messages = (
        await db.execute(
            select(Message)
            .where(Message.session_id == ticket.session_id)
            .order_by(Message.created_at, Message.id)
        )
    ).scalars().all()
    rating = await db.scalar(
        select(TicketRating).where(TicketRating.ticket_id == ticket_id)
    )
    return {
        "ticket": {
            "id": str(ticket.id),
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
            "priority": ticket.priority,
            "session_id": str(ticket.session_id),
            "claimed_at": ticket.claimed_at,
            "closed_at": ticket.closed_at,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
        },
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ],
        "rating": {"score": rating.score, "comment": rating.comment} if rating else None,
        "can_rate": ticket.status == "closed" and rating is None,
    }


async def rate_my_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    score: int,
    comment: str | None,
) -> TicketRating:
    """用户端工单评价（P2 接口预留）：closed 且未评价才可评一次。"""
    ticket = await _get_owned_ticket(db, user, ticket_id)
    if ticket.status != "closed":
        raise ConflictError("工单关闭后才能评价")
    existing = await db.scalar(
        select(TicketRating).where(TicketRating.ticket_id == ticket_id)
    )
    if existing is not None:
        raise ConflictError("该工单已评价，不能重复评价")
    rating = TicketRating(
        ticket_id=ticket_id, user_id=user.id, score=score, comment=comment
    )
    db.add(rating)
    await db.commit()
    await db.refresh(rating)
    return rating


async def mark_my_session_read(
    db: AsyncSession,
    user: User,
    session_id: uuid.UUID,
    last_read_message_id: uuid.UUID | None = None,
) -> dict:
    """用户端已读游标（12 §5.7）：归属校验后更新。"""
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise NotFoundError("会话不存在")
    _ensure_owned(session, user)
    await read_service.upsert_read_cursor(
        db, session_id, "user", user.id, last_read_message_id
    )
    return {"ok": True}
