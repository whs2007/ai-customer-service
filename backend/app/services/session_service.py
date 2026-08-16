"""会话与消息服务（08 §4.4 持久化 / 03 §6.5 刷新恢复）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.mask import mask_object
from app.models.message import Message
from app.models.session import ChatSession
from app.models.trace_log import TraceLog
from app.models.user import User


async def get_or_create_session(
    db: AsyncSession,
    session_id: uuid.UUID | None,
    user: User,
    kb_ids: list[str],
) -> ChatSession:
    if session_id is not None:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise NotFoundError("会话不存在")
        return session
    session = ChatSession(user_id=user.id, kb_ids=kb_ids)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession,
    page: int,
    page_size: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    intent: str | None = None,
    status: str | None = None,
    transferred: bool | None = None,
    keyword: str | None = None,
    annotated: bool | None = None,
) -> tuple[list[dict], int]:
    """会话列表（10 §4.1 筛选：时间/意图/状态/是否转人工/关键词/标注状态）。

    是否转人工以 status=transferred 判定（B4 转人工即置 transferred）。
    """
    stmt = select(ChatSession)
    count_stmt = select(func.count()).select_from(ChatSession)

    if start_date is not None:
        stmt = stmt.where(ChatSession.created_at >= start_date)
        count_stmt = count_stmt.where(ChatSession.created_at >= start_date)
    if end_date is not None:
        stmt = stmt.where(ChatSession.created_at <= end_date)
        count_stmt = count_stmt.where(ChatSession.created_at <= end_date)
    if status:
        stmt = stmt.where(ChatSession.status == status)
        count_stmt = count_stmt.where(ChatSession.status == status)
    if transferred is True:
        stmt = stmt.where(ChatSession.status == "transferred")
        count_stmt = count_stmt.where(ChatSession.status == "transferred")
    elif transferred is False:
        stmt = stmt.where(ChatSession.status != "transferred")
        count_stmt = count_stmt.where(ChatSession.status != "transferred")
    if intent:
        sub = select(Message.session_id).where(
            Message.role == "assistant", Message.intent == intent
        )
        stmt = stmt.where(ChatSession.id.in_(sub))
        count_stmt = count_stmt.where(ChatSession.id.in_(sub))
    if keyword:
        kw = f"%{keyword}%"
        sub = select(Message.session_id).where(Message.content.ilike(kw))
        stmt = stmt.where(
            or_(cast(ChatSession.id, String).ilike(kw), ChatSession.id.in_(sub))
        )
        count_stmt = count_stmt.where(
            or_(cast(ChatSession.id, String).ilike(kw), ChatSession.id.in_(sub))
        )
    if annotated is not None:
        from app.models.session_annotation import SessionAnnotation

        sub = select(SessionAnnotation.session_id)
        if annotated:
            stmt = stmt.where(ChatSession.id.in_(sub))
            count_stmt = count_stmt.where(ChatSession.id.in_(sub))
        else:
            stmt = stmt.where(ChatSession.id.not_in(sub))
            count_stmt = count_stmt.where(ChatSession.id.not_in(sub))

    total = await db.scalar(count_stmt) or 0
    result = await db.execute(
        stmt.order_by(ChatSession.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    sessions = list(result.scalars().all())
    return await _enrich_sessions(db, sessions), total


async def _enrich_sessions(
    db: AsyncSession, sessions: list[ChatSession]
) -> list[dict]:
    """批量补全列表派生字段（消息数/意图/工单号/标注状态）。"""
    from app.models.session_annotation import SessionAnnotation
    from app.models.ticket import Ticket

    if not sessions:
        return []
    ids = [s.id for s in sessions]

    counts: dict[uuid.UUID, int] = {
        session_id: count
        for session_id, count in (
            await db.execute(
                select(Message.session_id, func.count(Message.id))
                .where(Message.session_id.in_(ids))
                .group_by(Message.session_id)
            )
        ).all()
    }
    last_intents: dict[uuid.UUID, str | None] = {
        session_id: intent
        for session_id, intent in (
            await db.execute(
                select(Message.session_id, Message.intent)
                .where(
                    Message.session_id.in_(ids),
                    Message.role == "assistant",
                    Message.intent.is_not(None),
                )
                .order_by(Message.created_at.desc())
            )
        ).all()
    }
    ticket_map: dict[uuid.UUID, str] = {}
    rows = await db.execute(
        select(Ticket.session_id, Ticket.ticket_no)
        .where(Ticket.session_id.in_(ids))
        .order_by(Ticket.created_at.desc())
    )
    for session_id, ticket_no in rows.all():
        ticket_map.setdefault(session_id, ticket_no)
    annotated_ids = set(
        (
            await db.execute(
                select(SessionAnnotation.session_id).where(
                    SessionAnnotation.session_id.in_(ids)
                )
            )
        ).scalars().all()
    )

    items = []
    for s in sessions:
        items.append(
            {
                "id": s.id,
                "status": s.status,
                "channel": s.channel,
                "kb_ids": s.kb_ids,
                "escalation_count": s.escalation_count,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "message_count": counts.get(s.id, 0),
                "intent": last_intents.get(s.id),
                "transferred": s.status == "transferred",
                "ticket_no": ticket_map.get(s.id),
                "annotated": s.id in annotated_ids,
            }
        )
    return items


async def get_session_with_messages(
    db: AsyncSession, session_id: uuid.UUID
) -> tuple[ChatSession, list[Message]]:
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise NotFoundError("会话不存在")
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at, Message.id)
    )
    return session, list(result.scalars().all())


async def get_recent_messages(
    db: AsyncSession, session_id: uuid.UUID, limit: int = 10
) -> list[Message]:
    """上下文策略：携带最近 10 条消息（08 §4.4）。"""
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def append_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    intent: str | None = None,
    cited_chunk_ids: list | None = None,
) -> Message:
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        cited_chunk_ids=cited_chunk_ids or [],
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def save_trace(
    db: AsyncSession,
    session_id: uuid.UUID,
    request_id: str,
    steps: list,
    latency_ms: int,
    message_id: uuid.UUID | None = None,
    tokens: dict | None = None,
) -> TraceLog:
    log = TraceLog(
        session_id=session_id,
        message_id=message_id,
        request_id=request_id,
        steps=mask_object(steps),
        latency_ms=latency_ms,
        tokens=mask_object(tokens) if tokens else None,
    )
    db.add(log)
    await db.commit()
    return log
