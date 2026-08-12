"""系统配置服务（08 §4.7 / 03 §7 意图规则可配置）。"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting
from app.schemas.settings import ChunkingConfig, EscalationConfig, PromptConfig


async def get_setting(db: AsyncSession, key: str) -> Setting | None:
    return await db.get(Setting, key)


async def set_setting(
    db: AsyncSession,
    key: str,
    value: dict,
    group: str,
    description: str | None = None,
    is_secret: bool = False,
) -> Setting:
    setting = await db.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=value, group=group)
        db.add(setting)
    setting.value = value
    setting.group = group
    if description is not None:
        setting.description = description
    setting.is_secret = is_secret
    await db.commit()
    await db.refresh(setting)
    return setting


async def get_intent_rules(db: AsyncSession) -> dict:
    """合并默认意图规则与 settings(group=intent) 覆盖。"""
    from app.agents.intent import DEFAULT_INTENT_RULES

    defaults = copy.deepcopy(DEFAULT_INTENT_RULES)
    setting = await get_setting(db, "intent_rules")
    if setting and setting.group == "intent" and isinstance(setting.value, dict):
        value: dict[str, Any] = setting.value
        for category, keywords in value.get("keywords", {}).items():
            if isinstance(keywords, list) and keywords:
                defaults["keywords"][category] = [str(k) for k in keywords]
        if value.get("order_no_pattern"):
            defaults["order_no_pattern"] = str(value["order_no_pattern"])
    return defaults


async def set_intent_rules(db: AsyncSession, rules: dict) -> Setting:
    """保存意图规则（仅 admin）。"""
    return await set_setting(
        db,
        key="intent_rules",
        value=rules,
        group="intent",
        description="意图分类关键词与订单号规则",
    )


async def get_prompt_config(db: AsyncSession) -> PromptConfig:
    defaults = PromptConfig()
    setting = await get_setting(db, "prompt_config")
    if setting and setting.group == "prompt" and isinstance(setting.value, dict):
        return PromptConfig(**{**defaults.model_dump(), **setting.value})
    return defaults


async def set_prompt_config(db: AsyncSession, cfg: PromptConfig) -> Setting:
    return await set_setting(
        db,
        key="prompt_config",
        value=cfg.model_dump(),
        group="prompt",
        description="系统人设 / 兜底话术 / 转人工判定规则",
    )


async def get_escalation_config(db: AsyncSession) -> EscalationConfig:
    defaults = EscalationConfig()
    setting = await get_setting(db, "escalation_config")
    if setting and setting.group == "escalation" and isinstance(setting.value, dict):
        return EscalationConfig(**{**defaults.model_dump(), **setting.value})
    return defaults


async def set_escalation_config(db: AsyncSession, cfg: EscalationConfig) -> Setting:
    return await set_setting(
        db,
        key="escalation_config",
        value=cfg.model_dump(),
        group="escalation",
        description="转人工条件与工单优先级规则",
    )


async def get_chunking_config(db: AsyncSession) -> ChunkingConfig:
    defaults = ChunkingConfig()
    setting = await get_setting(db, "chunking_config")
    if setting and setting.group == "chunking" and isinstance(setting.value, dict):
        return ChunkingConfig(**{**defaults.model_dump(), **setting.value})
    return defaults


async def set_chunking_config(db: AsyncSession, cfg: ChunkingConfig) -> Setting:
    return await set_setting(
        db,
        key="chunking_config",
        value=cfg.model_dump(),
        group="chunking",
        description="普通文本分块参数",
    )
