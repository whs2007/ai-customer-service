"""已读游标服务（11 §5.3 / 开发文档 01 §5.7）：未读数按对方角色计算。"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.message import Message
from app.models.session_read import SessionRead

# 未读数口径：user 看 agent/assistant 消息；agent 看 user 消息（11 §5.3）
_OPPOSITE_ROLES: dict[str, tuple[str, ...]] = {
    "user": ("agent", "assistant"),
    "agent": ("user",),
}


async def upsert_read_cursor(
    db: AsyncSession,
    session_id: uuid.UUID,
    reader_role: str,
    reader_id: uuid.UUID,
    last_read_message_id: uuid.UUID | None = None,
) -> SessionRead:
    """更新已读游标；未指定消息时取会话最新消息。"""
    if last_read_message_id is None:
        latest = await db.scalar(
            select(Message.id)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        last_read_message_id = latest

    # 【修复 M4】原子 upsert：INSERT ... ON CONFLICT DO UPDATE，避免并发已读触发唯一约束 500
    stmt = pg_insert(SessionRead).values(
        session_id=session_id,
        reader_role=reader_role,
        reader_id=reader_id,
        last_read_message_id=last_read_message_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["session_id", "reader_role", "reader_id"],
        set_={
            "last_read_message_id": stmt.excluded.last_read_message_id,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()
    cursor = await db.scalar(
        select(SessionRead).where(
            SessionRead.session_id == session_id,
            SessionRead.reader_role == reader_role,
            SessionRead.reader_id == reader_id,
        )
    )
    assert cursor is not None
    return cursor


async def get_unread_count(
    db: AsyncSession,
    session_id: uuid.UUID,
    reader_role: str,
    reader_id: uuid.UUID,
) -> int:
    """未读数 = 对方角色消息中创建时间晚于游标的消息数。"""
    opposite = _OPPOSITE_ROLES.get(reader_role)
    if not opposite:
        return 0
    cursor = await db.scalar(
        select(SessionRead).where(
            SessionRead.session_id == session_id,
            SessionRead.reader_role == reader_role,
            SessionRead.reader_id == reader_id,
        )
    )
    stmt = select(func.count()).select_from(Message).where(
        Message.session_id == session_id,
        Message.role.in_(opposite),
    )
    if cursor is not None and cursor.last_read_message_id is not None:
        last_read = await db.get(Message, cursor.last_read_message_id)
        if last_read is not None:
            # 【修复 L2】按 (created_at, id) 元组比较，避免同微秒消息漏计
            stmt = stmt.where(
                or_(
                    Message.created_at > last_read.created_at,
                    and_(
                        Message.created_at == last_read.created_at,
                        Message.id > last_read.id,
                    ),
                )
            )
    return await db.scalar(stmt) or 0


async def get_unread_counts(
    db: AsyncSession,
    session_ids: list[uuid.UUID],
    reader_role: str,
    reader_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    """批量未读数（P1-3）：单条 SQL 按会话聚合，替代逐会话 N+1 查询。"""
    if not session_ids:
        return {}
    opposite = _OPPOSITE_ROLES.get(reader_role)
    if not opposite:
        return {sid: 0 for sid in session_ids}
    last_msg = aliased(Message, name="last_read_msg")
    stmt = (
        select(Message.session_id, func.count())
        .select_from(Message)
        .outerjoin(
            SessionRead,
            (SessionRead.session_id == Message.session_id)
            & (SessionRead.reader_role == reader_role)
            & (SessionRead.reader_id == reader_id),
        )
        .outerjoin(last_msg, last_msg.id == SessionRead.last_read_message_id)
        .where(
            Message.session_id.in_(session_ids),
            Message.role.in_(opposite),
            or_(
                SessionRead.last_read_message_id.is_(None),
                or_(
                    Message.created_at > last_msg.created_at,
                    and_(
                        Message.created_at == last_msg.created_at,
                        Message.id > last_msg.id,
                    ),
                ),
            ),
        )
        .group_by(Message.session_id)
    )
    rows = (await db.execute(stmt)).all()
    counts = {sid: cnt for sid, cnt in rows}
    return {sid: counts.get(sid, 0) for sid in session_ids}
