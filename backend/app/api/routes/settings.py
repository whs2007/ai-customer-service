"""设置接口（B4：意图规则 + 模型配置列表/默认切换；完整设置页见 B6）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import ResponseModel, ok
from app.models.user import Role, User
from app.schemas.chat import (
    IntentRulesUpdate,
    ModelProfileCreate,
    ModelProfileOut,
    ModelProfileTestOut,
    ModelProfileUpdate,
)
from app.schemas.settings import (
    ChannelConfigOut,
    ChannelConfigUpdate,
    ChunkingConfig,
    EscalationConfig,
    PromptConfig,
)
from app.services import model_profile_service, settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class SensitiveWordsUpdate(BaseModel):
    """内容审核敏感词配置（08 §8：管理员在线维护）。"""

    words: list[str] = Field(default_factory=list, max_length=200)


@router.get("/intent", response_model=ResponseModel)
async def get_intent_rules(
    _: User = Depends(require_roles(Role.ADMIN)),
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


@router.post("/model-profiles", response_model=ResponseModel[ModelProfileOut])
async def create_model_profile(
    payload: ModelProfileCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    profile = await model_profile_service.create_profile(db, payload)
    return ok(
        data=ModelProfileOut(
            id=profile.id,
            name=profile.name,
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key="sk-***" if profile.api_key_enc else "",
            temperature=profile.temperature,
            top_p=profile.top_p,
            max_tokens=profile.max_tokens,
            role=profile.role,
            is_default=profile.is_default,
            enabled=profile.enabled,
        ),
        message="创建成功",
    )


@router.put("/model-profiles/{profile_id}", response_model=ResponseModel[ModelProfileOut])
async def update_model_profile(
    profile_id: uuid.UUID,
    payload: ModelProfileUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    profile = await model_profile_service.update_profile(db, profile_id, payload)
    return ok(
        data=ModelProfileOut(
            id=profile.id,
            name=profile.name,
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key="sk-***" if profile.api_key_enc else "",
            temperature=profile.temperature,
            top_p=profile.top_p,
            max_tokens=profile.max_tokens,
            role=profile.role,
            is_default=profile.is_default,
            enabled=profile.enabled,
        ),
        message="更新成功",
    )


@router.delete("/model-profiles/{profile_id}", response_model=ResponseModel)
async def delete_model_profile(
    profile_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await model_profile_service.delete_profile(db, profile_id)
    return ok(message="删除成功")


@router.post(
    "/model-profiles/{profile_id}/test",
    response_model=ResponseModel[ModelProfileTestOut],
)
async def test_model_profile(
    profile_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    result = await model_profile_service.test_profile(db, profile_id)
    return ok(data=result)


@router.put("/model-profiles/{profile_id}/activate", response_model=ResponseModel)
async def activate_model_profile(
    profile_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    profile = await model_profile_service.set_default_profile(db, profile_id)
    return ok(message=f"已将 {profile.name} 设为默认 {profile.role} 配置")


@router.get("/prompt", response_model=ResponseModel[PromptConfig])
async def get_prompt_config(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await settings_service.get_prompt_config(db))


@router.put("/prompt", response_model=ResponseModel[PromptConfig])
async def update_prompt_config(
    payload: PromptConfig,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await settings_service.set_prompt_config(db, payload)
    return ok(data=payload, message="Prompt 配置已更新")


@router.get("/escalation", response_model=ResponseModel[EscalationConfig])
async def get_escalation_config(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await settings_service.get_escalation_config(db))


@router.put("/escalation", response_model=ResponseModel[EscalationConfig])
async def update_escalation_config(
    payload: EscalationConfig,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await settings_service.set_escalation_config(db, payload)
    return ok(data=payload, message="客服规则已更新")


@router.get("/chunking", response_model=ResponseModel[ChunkingConfig])
async def get_chunking_config(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await settings_service.get_chunking_config(db))


@router.put("/chunking", response_model=ResponseModel[ChunkingConfig])
async def update_chunking_config(
    payload: ChunkingConfig,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await settings_service.set_chunking_config(db, payload)
    return ok(data=payload, message="分块参数已更新")


@router.get("/moderation/words", response_model=ResponseModel)
async def get_moderation_words(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """读取内容审核敏感词（本地兜底词表）。"""
    from app.core.moderation import get_sensitive_words

    return ok(data={"words": await get_sensitive_words(db)})


@router.put("/moderation/words", response_model=ResponseModel)
async def update_moderation_words(
    payload: SensitiveWordsUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """覆盖内容审核敏感词（管理员在线维护，≤200 条）。"""
    from app.core.moderation import set_sensitive_words

    await set_sensitive_words(db, payload.words)
    return ok(message="敏感词已更新")


@router.get("/channel", response_model=ResponseModel[ChannelConfigOut])
async def get_channel_config(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """读取渠道配置（11 §8 / 开发文档 01 §6.2）。"""
    config = await settings_service.get_channel_config(db)
    if config is None:
        config = ChannelConfigOut(channel="web_user", default_kb_ids=[])
    return ok(data=config)


@router.put("/channel", response_model=ResponseModel[ChannelConfigOut])
async def update_channel_config(
    payload: ChannelConfigUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """保存渠道配置（admin；用户端新会话立即生效）。"""
    config = await settings_service.set_channel_config(db, payload)
    return ok(
        data=ChannelConfigOut(
            channel=config.channel,
            default_kb_ids=[str(x) for x in (config.default_kb_ids or [])],
            allow_human=config.allow_human,
            business_hours=config.business_hours,
            updated_at=config.updated_at,
        ),
        message="渠道配置已保存",
    )
