"""知识库接口（08 §6.2 / 04 §1–2）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import ResponseModel, ok
from app.models.user import Role, User
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseDetailOut,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("", response_model=ResponseModel[list[KnowledgeBaseOut]])
async def list_knowledge_bases(
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await knowledge_service.list_knowledge_bases(db, user))


@router.post("", response_model=ResponseModel[KnowledgeBaseOut])
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    kb = await knowledge_service.create_knowledge_base(db, payload, user)
    return ok(
        data=KnowledgeBaseOut(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            doc_count=0,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        ),
        message="创建成功",
    )


@router.get("/{kb_id}", response_model=ResponseModel[KnowledgeBaseDetailOut])
async def get_knowledge_base(
    kb_id: uuid.UUID,
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    kb = await knowledge_service.ensure_kb_accessible(db, kb_id, user)
    return ok(data=KnowledgeBaseDetailOut.model_validate(kb))


@router.put("/{kb_id}", response_model=ResponseModel[KnowledgeBaseOut])
async def update_knowledge_base(
    kb_id: uuid.UUID,
    payload: KnowledgeBaseUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    kb = await knowledge_service.update_knowledge_base(db, kb_id, payload)
    return ok(
        data=KnowledgeBaseOut(
            id=kb.id, name=kb.name, description=kb.description, doc_count=0,
            created_at=kb.created_at, updated_at=kb.updated_at,
        ),
        message="更新成功",
    )


@router.delete("/{kb_id}", response_model=ResponseModel)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await knowledge_service.delete_knowledge_base(
        db, kb_id, user, ip=request.client.host if request.client else None
    )
    return ok(message="删除成功")
