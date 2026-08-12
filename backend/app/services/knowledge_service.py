"""知识库业务逻辑（08 §4.2）：CRUD、软删除、级联清空。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.knowledge import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBaseUpdate
from app.services.audit_service import write_audit


async def list_knowledge_bases(db: AsyncSession) -> list[KnowledgeBaseOut]:
    """列表（含文档数，排除软删除）。"""
    stmt = (
        select(KnowledgeBase, func.count(Document.id).label("doc_count"))
        .outerjoin(
            Document,
            and_(Document.kb_id == KnowledgeBase.id, Document.deleted_at.is_(None)),
        )
        .where(KnowledgeBase.deleted_at.is_(None))
        .group_by(KnowledgeBase.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        KnowledgeBaseOut(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            doc_count=doc_count,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        for kb, doc_count in rows
    ]


async def get_knowledge_base(db: AsyncSession, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None or kb.deleted_at is not None:
        raise NotFoundError("知识库不存在")
    return kb


async def create_knowledge_base(
    db: AsyncSession, payload: KnowledgeBaseCreate, user: User
) -> KnowledgeBase:
    existing = await db.scalar(
        select(KnowledgeBase).where(KnowledgeBase.name == payload.name)
    )
    if existing is not None:
        raise ConflictError("该名称已存在")
    kb = KnowledgeBase(
        name=payload.name.strip(),
        description=payload.description.strip(),
        created_by=user.id,
    )
    db.add(kb)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("该名称已存在") from exc
    await db.refresh(kb)
    return kb


async def update_knowledge_base(
    db: AsyncSession, kb_id: uuid.UUID, payload: KnowledgeBaseUpdate
) -> KnowledgeBase:
    kb = await get_knowledge_base(db, kb_id)
    conflict = await db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.name == payload.name.strip(), KnowledgeBase.id != kb_id
        )
    )
    if conflict is not None:
        raise ConflictError("该名称已存在")
    kb.name = payload.name.strip()
    kb.description = payload.description.strip()
    await db.commit()
    await db.refresh(kb)
    return kb


async def delete_knowledge_base(
    db: AsyncSession,
    kb_id: uuid.UUID,
    user: User,
    ip: str | None = None,
) -> None:
    """高危操作：先物理清空切片与文档，再软删除知识库（04 §1.4 二次确认提示）。"""
    kb = await get_knowledge_base(db, kb_id)
    await db.execute(delete(Chunk).where(Chunk.kb_id == kb_id))
    await db.execute(delete(Document).where(Document.kb_id == kb_id))
    kb.deleted_at = datetime.now(timezone.utc)
    await write_audit(
        db,
        action="delete_knowledge_base",
        user_id=str(user.id),
        ip=ip,
        target_type="knowledge_base",
        target_id=str(kb_id),
        detail={"name": kb.name},
    )
    await db.commit()

