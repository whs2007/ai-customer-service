"""文档业务逻辑（08 §4.2）：上传登记、异步处理派发、列表/删除/重新解析。"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.services.audit_service import write_audit

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def list_documents(
    db: AsyncSession,
    kb_id: uuid.UUID,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Document], int]:
    stmt = select(Document).where(
        Document.kb_id == kb_id, Document.deleted_at.is_(None)
    )
    count_stmt = select(func.count()).select_from(Document).where(
        Document.kb_id == kb_id, Document.deleted_at.is_(None)
    )
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Document.file_name.ilike(like))
        count_stmt = count_stmt.where(Document.file_name.ilike(like))
    total = await db.scalar(count_stmt) or 0
    result = await db.execute(
        stmt.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_document(db: AsyncSession, doc_id: uuid.UUID) -> Document:
    doc = await db.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise NotFoundError("文档不存在")
    return doc


async def create_document_record(
    db: AsyncSession,
    kb_id: uuid.UUID,
    file_name: str,
    file_size: int,
    file_url: str,
) -> Document:
    ext = Path(file_name).suffix.lower().lstrip(".")
    doc = Document(
        kb_id=kb_id,
        file_name=file_name,
        file_type=ext,
        file_size=file_size,
        file_url=file_url,
        status="uploading",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def process_document_job(doc_id: str) -> None:
    """派发文档处理：inline 进程内异步 / celery 入队（TASK_BACKEND，见 config）。"""
    settings = get_settings()
    if settings.task_backend == "celery":
        from app.workers.tasks import document_process_task

        document_process_task.delay(doc_id)
        logger.info("document_task_enqueued", doc_id=doc_id)
    else:
        from app.pipeline.importer import process_document

        await process_document(doc_id)


async def delete_document(
    db: AsyncSession,
    doc_id: uuid.UUID,
    user: User,
    ip: str | None = None,
) -> None:
    """删除文档：物理删除切片（含向量）与文档记录。"""
    doc = await get_document(db, doc_id)
    await db.execute(delete(Chunk).where(Chunk.doc_id == doc_id))
    await db.delete(doc)
    await write_audit(
        db,
        action="delete_document",
        user_id=str(user.id),
        ip=ip,
        target_type="document",
        target_id=str(doc_id),
        detail={"file_name": doc.file_name},
    )
    await db.commit()


async def reparse_document(
    db: AsyncSession, doc_id: uuid.UUID
) -> Document:
    """重新解析：重置状态并重新派发处理任务。"""
    doc = await get_document(db, doc_id)
    doc.status = "uploading"
    doc.error_message = None
    await db.commit()
    await db.refresh(doc)
    return doc

