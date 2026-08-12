"""知识库业务逻辑（08 §4.2）：CRUD、软删除、级联清空。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.knowledge import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBaseUpdate
from app.services.audit_service import write_audit


async def list_knowledge_bases(
    db: AsyncSession, user: User | None = None
) -> list[KnowledgeBaseOut]:
    """列表（含文档数，排除软删除；非 admin 按可见范围过滤，00 §3）。"""
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
    if user is not None and user.role != "admin":
        rows = [
            row
            for row in rows
            if _kb_visible(user, row[0].visibility, row[0].visible_roles, row[0].visible_user_ids)
        ]
    return [
        KnowledgeBaseOut(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            doc_count=doc_count,
            visibility=kb.visibility,
            visible_roles=kb.visible_roles,
            visible_user_ids=kb.visible_user_ids,
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


async def ensure_kb_accessible(
    db: AsyncSession, kb_id: uuid.UUID, user: User | None = None
) -> KnowledgeBase:
    """读取前资源级可见性校验（00 §3 / 08 §8 数据隔离）：admin 全见，
    agent/viewer 按 all/role/user 过滤，越权抛 40300。"""
    kb = await get_knowledge_base(db, kb_id)
    if user is not None and user.role != "admin":
        if not _kb_visible(user, kb.visibility, kb.visible_roles, kb.visible_user_ids):
            raise ForbiddenError("无权限访问该知识库")
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
        visibility=payload.visibility or "all",
        visible_roles=payload.visible_roles or [],
        visible_user_ids=payload.visible_user_ids or [],
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
    if payload.visibility is not None:
        kb.visibility = payload.visibility
    if payload.visible_roles is not None:
        kb.visible_roles = payload.visible_roles
    if payload.visible_user_ids is not None:
        kb.visible_user_ids = payload.visible_user_ids
    await db.commit()
    await db.refresh(kb)
    return kb


def _kb_visible(
    user: User,
    visibility: str,
    visible_roles: list,
    visible_user_ids: list,
) -> bool:
    """资源级可见性判定（00 §3 新增，供列表与检索共用）。"""
    if visibility == "all":
        return True
    if visibility == "role":
        return user.role in (visible_roles or [])
    if visibility == "user":
        return str(user.id) in [str(x) for x in (visible_user_ids or [])]
    return False


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
