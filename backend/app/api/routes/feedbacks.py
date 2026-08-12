"""引用反馈接口（08 §6.2 / 03 §4.4 新增）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import ResponseModel, ok
from app.models.user import Role, User
from app.schemas.chat import FeedbackCreate, FeedbackOut
from app.services.feedback_service import create_feedback

router = APIRouter(tags=["feedbacks"])


@router.post("/feedbacks", response_model=ResponseModel[FeedbackOut])
async def feedback(
    payload: FeedbackCreate,
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    feedback = await create_feedback(db, payload, user)
    return ok(data=FeedbackOut.model_validate(feedback), message="反馈已记录")

