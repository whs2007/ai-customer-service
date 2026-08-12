"""模型配置服务（08 §4.7；B4 仅列表/默认切换，完整 CRUD 留 B6）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.model_profile import ModelProfile
from app.schemas.chat import ModelProfileOut


def _mask_key(api_key_enc: str) -> str:
    return "sk-***" if api_key_enc else ""


async def list_profiles(db: AsyncSession) -> list[ModelProfileOut]:
    result = await db.execute(
        select(ModelProfile).order_by(ModelProfile.created_at)
    )
    return [
        ModelProfileOut(
            id=p.id,
            name=p.name,
            provider=p.provider,
            model=p.model,
            base_url=p.base_url,
            api_key=_mask_key(p.api_key_enc),
            temperature=p.temperature,
            top_p=p.top_p,
            max_tokens=p.max_tokens,
            role=p.role,
            is_default=p.is_default,
            enabled=p.enabled,
        )
        for p in result.scalars().all()
    ]


async def get_default_profile(db: AsyncSession) -> ModelProfile | None:
    result = await db.execute(
        select(ModelProfile)
        .where(ModelProfile.enabled.is_(True), ModelProfile.role == "chat")
        .order_by(ModelProfile.is_default.desc(), ModelProfile.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_profile(db: AsyncSession, profile_id: uuid.UUID) -> ModelProfile:
    profile = await db.get(ModelProfile, profile_id)
    if profile is None or not profile.enabled:
        raise NotFoundError("模型配置不存在或未启用")
    return profile


async def set_default_profile(db: AsyncSession, profile_id: uuid.UUID) -> ModelProfile:
    profile = await get_profile(db, profile_id)
    await db.execute(
        ModelProfile.__table__.update()
        .where(ModelProfile.role == "chat")
        .values(is_default=False)
    )
    profile.is_default = True
    await db.commit()
    await db.refresh(profile)
    return profile

