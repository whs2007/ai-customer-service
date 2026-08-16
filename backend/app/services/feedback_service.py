"""引用反馈服务（03 §4.4 / 08 §4.4 新增）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.eval_candidate import EvalCandidate
from app.models.message import Message
from app.models.message_feedback import MessageFeedback
from app.models.user import User
from app.schemas.chat import FeedbackCreate


async def create_feedback(
    db: AsyncSession, payload: FeedbackCreate, user: User
) -> MessageFeedback:
    message = await db.get(Message, payload.message_id)
    if message is None:
        raise NotFoundError("消息不存在")
    if str(message.session_id) != str(payload.session_id):
        raise BadRequestError("消息与会话不匹配")

    feedback = MessageFeedback(
        session_id=payload.session_id,
        message_id=payload.message_id,
        chunk_id=payload.chunk_id,
        action=payload.action,
        reason=payload.reason,
        user_id=user.id,
    )
    db.add(feedback)
    if payload.include_in_eval:
        await db.flush()  # 获取 feedback.id 供候选来源引用
        # 回流候选：问题取该消息之前最近的用户消息，期望答案取 AI 消息内容
        question = message.content[:500]
        msgs = (
            await db.execute(
                select(Message)
                .where(Message.session_id == payload.session_id)
                .order_by(Message.created_at)
            )
        ).scalars().all()
        for m in msgs:
            if m.id == message.id:
                break
            if m.role == "user":
                question = m.content
        db.add(
            EvalCandidate(
                question=question[:500],
                expected_answer=message.content,
                source="feedback",
                source_id=str(feedback.id) if feedback.id else None,
                message_id=message.id,
            )
        )
    await db.commit()
    await db.refresh(feedback)
    return feedback
