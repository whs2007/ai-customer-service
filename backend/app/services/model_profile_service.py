"""模型配置服务（08 §4.7：CRUD / 默认切换 / 测试连通）。"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import decrypt_secret, encrypt_secret
from app.models.model_profile import ModelProfile
from app.schemas.chat import (
    ModelProfileCreate,
    ModelProfileOut,
    ModelProfileTestOut,
    ModelProfileUpdate,
)


def _default_base_url(provider: str) -> str:
    return {
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "siliconflow": "https://api.siliconflow.cn/v1",
        "ollama": "http://localhost:11434/v1",
    }.get(provider, "https://api.openai.com/v1")


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
    await _clear_default(db, profile.role)
    profile.is_default = True
    await db.commit()
    await db.refresh(profile)
    return profile


async def _clear_default(db: AsyncSession, role: str) -> None:
    await db.execute(
        ModelProfile.__table__.update()
        .where(ModelProfile.role == role)
        .values(is_default=False)
    )


async def create_profile(
    db: AsyncSession, payload: ModelProfileCreate
) -> ModelProfile:
    existing = await db.scalar(
        select(ModelProfile).where(ModelProfile.name == payload.name.strip())
    )
    if existing is not None:
        raise ConflictError("配置名称已存在")
    profile = ModelProfile(
        name=payload.name.strip(),
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key_enc=encrypt_secret(payload.api_key),
        temperature=Decimal(str(payload.temperature)),
        top_p=Decimal(str(payload.top_p)),
        max_tokens=payload.max_tokens,
        role=payload.role,
        is_default=payload.is_default,
        enabled=payload.enabled,
    )
    db.add(profile)
    if payload.is_default:
        await _clear_default(db, payload.role)
    await db.commit()
    await db.refresh(profile)
    return profile


async def update_profile(
    db: AsyncSession, profile_id: uuid.UUID, payload: ModelProfileUpdate
) -> ModelProfile:
    profile = await db.get(ModelProfile, profile_id)
    if profile is None:
        raise NotFoundError("模型配置不存在")
    if payload.name is not None:
        conflict = await db.scalar(
            select(ModelProfile).where(
                ModelProfile.name == payload.name.strip(),
                ModelProfile.id != profile_id,
            )
        )
        if conflict is not None:
            raise ConflictError("配置名称已存在")
        profile.name = payload.name.strip()
    if payload.provider is not None:
        profile.provider = payload.provider
    if payload.model is not None:
        profile.model = payload.model
    if payload.base_url is not None:
        profile.base_url = payload.base_url or None
    if payload.api_key:
        profile.api_key_enc = encrypt_secret(payload.api_key)
    if payload.temperature is not None:
        profile.temperature = Decimal(str(payload.temperature))
    if payload.top_p is not None:
        profile.top_p = Decimal(str(payload.top_p))
    if payload.max_tokens is not None:
        profile.max_tokens = payload.max_tokens
    if payload.role is not None and payload.role != profile.role:
        was_default = profile.is_default
        profile.role = payload.role
        if was_default:
            profile.is_default = False
            await _clear_default(db, profile.role)
    if payload.enabled is not None:
        profile.enabled = payload.enabled
    await db.commit()
    await db.refresh(profile)
    return profile


async def delete_profile(db: AsyncSession, profile_id: uuid.UUID) -> None:
    profile = await db.get(ModelProfile, profile_id)
    if profile is None:
        raise NotFoundError("模型配置不存在")
    if profile.is_default:
        raise BadRequestError("默认配置不能删除，请先切换默认")
    await db.delete(profile)
    await db.commit()


async def test_profile(
    db: AsyncSession, profile_id: uuid.UUID
) -> ModelProfileTestOut:
    """测试连通：按用途调用对应端点（chat/embedding/rerank）。"""
    profile = await get_profile(db, profile_id)
    base_url = (profile.base_url or _default_base_url(profile.provider)).rstrip("/")
    api_key = decrypt_secret(profile.api_key_enc)
    if not api_key and profile.provider != "ollama":
        return ModelProfileTestOut(ok=False, message="未配置 API Key")
    headers = (
        {"Authorization": f"Bearer {api_key}"}
        if api_key
        else {}
    )
    started = time.perf_counter()
    try:
        if profile.role == "chat":
            url = f"{base_url}/chat/completions"
            payload = {
                "model": profile.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
        elif profile.role == "embedding":
            url = f"{base_url}/embeddings"
            payload = {"model": profile.model, "input": "ping"}
        else:
            url = f"{base_url}/rerank"
            payload = {"model": profile.model, "query": "ping", "documents": ["ping"]}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return ModelProfileTestOut(
            ok=False,
            message=f"连接失败：{exc.__class__.__name__}",
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ModelProfileTestOut(ok=True, latency_ms=latency_ms, message="连接成功")
