"""会话人工标注服务（10 §4.4）：标注 upsert + 纳入评测集 → B4.5 评测候选。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_candidate import EvalCandidate
from app.models.message import Message
from app.models.session_annotation import SessionAnnotation
from app.models.user import User
from app.schemas.chat import AnnotationCreate


async def upsert_annotation(
    db: AsyncSession,
    session_id: uuid.UUID,
    payload: AnnotationCreate,
    user: User,
) -> SessionAnnotation:
    annotation = await db.scalar(
        select(SessionAnnotation).where(SessionAnnotation.session_id == session_id)
    )
    if annotation is None:
        annotation = SessionAnnotation(session_id=session_id, user_id=user.id)
        db.add(annotation)
    annotation.tags = [t.strip()[:20] for t in payload.tags if t.strip()][:10]
    annotation.note = payload.note
    annotation.include_in_eval = payload.include_in_eval
    annotation.eval_set_id = payload.eval_set_id
    annotation.user_id = user.id

    if payload.include_in_eval:
        # 回流候选：问题取首条用户消息，期望答案取最后一条 AI 消息（10 §4.4 → 09 §8）
        messages = (
            await db.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at)
            )
        ).scalars().all()
        question = next(
            (m.content for m in messages if m.role == "user"),
            str(session_id),
        )
        expected = next(
            (
                m.content
                for m in reversed(messages)
                if m.role == "assistant" and m.content
            ),
            "",
        )
        candidate = await db.scalar(
            select(EvalCandidate).where(
                EvalCandidate.source == "annotation",
                EvalCandidate.source_id == str(session_id),
                EvalCandidate.status == "pending",
            )
        )
        if candidate is None:
            candidate = EvalCandidate(
                question=question[:500],
                expected_answer=expected,
                source="annotation",
                source_id=str(session_id),
                message_id=messages[-1].id if messages else None,
            )
            db.add(candidate)
        else:
            candidate.question = question[:500]
            candidate.expected_answer = expected
            candidate.message_id = messages[-1].id if messages else None

    await db.commit()
    await db.refresh(annotation)
    return annotation

