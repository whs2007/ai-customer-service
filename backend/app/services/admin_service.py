"""系统管理服务（B6a：日志审计 / 全量重建向量 / 知识库导出）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase


async def list_audit_logs(
    db: AsyncSession,
    action: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditLog], int]:
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    total = await db.scalar(count_stmt) or 0
    result = await db.execute(
        stmt.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def rebuild_vectors(db: AsyncSession) -> dict:
    """全量重建向量索引：逐文档重新解析 + 重新向量化（B6a 数据管理）。

    说明：无 Redis/Celery 时同步执行，大库耗时长；后续可切 Celery 任务。
    """
    from app.pipeline.importer import process_document

    docs = (
        await db.execute(
            select(Document).where(Document.deleted_at.is_(None))
        )
    ).scalars().all()
    total = len(docs)
    succeeded = 0
    failed = 0
    for doc in docs:
        result = await process_document(str(doc.id))
        if result is not None and result.status == "completed":
            succeeded += 1
        else:
            failed += 1
    return {"total": total, "succeeded": succeeded, "failed": failed}


async def export_knowledge_bases(db: AsyncSession) -> dict:
    """导出知识库（备份/迁移用）：知识库 + 文档 + Chunk 全量文本（不含向量）。"""
    kbs = (
        await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.deleted_at.is_(None))
        )
    ).scalars().all()
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "knowledge_bases": [],
    }
    for kb in kbs:
        docs = (
            await db.execute(
                select(Document).where(
                    Document.kb_id == kb.id, Document.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        kb_item = {
            "id": str(kb.id),
            "name": kb.name,
            "description": kb.description,
            "visibility": kb.visibility,
            "documents": [],
        }
        for doc in docs:
            chunks = (
                await db.execute(
                    select(Chunk)
                    .where(Chunk.doc_id == doc.id)
                    .order_by(Chunk.chunk_index)
                )
            ).scalars().all()
            kb_item["documents"].append(
                {
                    "id": str(doc.id),
                    "file_name": doc.file_name,
                    "file_type": doc.file_type,
                    "status": doc.status,
                    "chunks": [
                        {
                            "chunk_index": c.chunk_index,
                            "question": c.question,
                            "answer": c.answer,
                            "category": c.category,
                            "page": c.page,
                            "row": c.row,
                            "tags": c.tags,
                        }
                        for c in chunks
                    ],
                }
            )
        payload["knowledge_bases"].append(kb_item)
    return payload

