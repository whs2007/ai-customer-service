"""引用反馈服务（03 §4.4 / 08 §4.4 新增）。"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
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
    await db.commit()
    await db.refresh(feedback)
    return feedback

