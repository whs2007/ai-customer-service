"""设置接口（B4：意图规则 + 模型配置列表/默认切换；完整设置页见 B6）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import ResponseModel, ok
from app.models.user import Role, User
from app.schemas.chat import IntentRulesUpdate, ModelProfileOut
from app.services import model_profile_service, settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/intent", response_model=ResponseModel)
async def get_intent_rules(
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    rules = await settings_service.get_intent_rules(db)
    return ok(data=rules)


@router.put("/intent", response_model=ResponseModel)
async def update_intent_rules(
    payload: IntentRulesUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    current = await settings_service.get_intent_rules(db)
    if payload.keywords:
        for category, keywords in payload.keywords.items():
            existing = current["keywords"].get(category, [])
            current["keywords"][category] = list(
                dict.fromkeys(existing + [k for k in keywords if k])
            )
    if payload.order_no_pattern:
        current["order_no_pattern"] = payload.order_no_pattern
    await settings_service.set_intent_rules(db, current)
    return ok(message="意图规则已更新")


@router.get("/model-profiles", response_model=ResponseModel[list[ModelProfileOut]])
async def list_model_profiles(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    profiles = await model_profile_service.list_profiles(db)
    return ok(data=profiles)


@router.put("/model-profiles/{profile_id}/activate", response_model=ResponseModel)
async def activate_model_profile(
    profile_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    profile = await model_profile_service.set_default_profile(db, profile_id)
    return ok(message=f"已将 {profile.name} 设为默认对话模型")
