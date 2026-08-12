"""会话与消息服务（08 §4.4 持久化 / 03 §6.5 刷新恢复）。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.message import Message, MessageRole
from app.models.session import ChatSession, SessionStatus
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
        if session.status == SessionStatus.TRANSFERRED.value:
            raise BadRequestError("该会话已转人工，AI 不再接管，请新建会话")
        return session
    session = ChatSession(user_id=user.id, kb_ids=kb_ids)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession, page: int, page_size: int
) -> tuple[list[ChatSession], int]:
    total = await db.scalar(select(func.count()).select_from(ChatSession)) or 0
    result = await db.execute(
        select(ChatSession)
        .order_by(ChatSession.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


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
) -> TraceLog:
    log = TraceLog(
        session_id=session_id,
        message_id=message_id,
        request_id=request_id,
        steps=steps,
        latency_ms=latency_ms,
    )
    db.add(log)
    await db.commit()
    return log

