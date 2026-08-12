"""入库编排：解析 → 切片 → 批量向量化 → 更新文档状态（08 §3.2 数据流）。"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.chunk import Chunk
from app.models.document import Document
from app.pipeline.parser import parse_document
from app.rag.embeddings import EmbeddingClient

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def process_document(doc_id: str | uuid.UUID) -> Document | None:
    """文档处理主流程：uploading → parsing → embedding → completed/failed。"""
    session_factory = get_session_factory()
    async with session_factory() as db:
        doc_id = uuid.UUID(str(doc_id)) if not isinstance(doc_id, uuid.UUID) else doc_id
        doc = await db.get(Document, doc_id)
        if doc is None:
            logger.warning("document_not_found", doc_id=str(doc_id))
            return None

        try:
            doc.status = "parsing"
            doc.error_message = None
            await db.commit()

            records = parse_document(Path(doc.file_url), doc.file_type)

            # 重新解析时先清空旧切片与向量
            await db.execute(delete(Chunk).where(Chunk.doc_id == doc.id))
            doc.status = "embedding"
            await db.commit()

            embedding_client = EmbeddingClient(get_settings())
            questions = [r["question"] for r in records]
            vectors = await embedding_client.embed_texts(questions)

            for index, (record, vector) in enumerate(zip(records, vectors), start=1):
                db.add(
                    Chunk(
                        doc_id=doc.id,
                        kb_id=doc.kb_id,
                        chunk_index=index,
                        question=record["question"],
                        answer=record["answer"],
                        category=record.get("category"),
                        page=record.get("page"),
                        row=record.get("row"),
                        word_count=len(record["answer"]),
                        tags=record.get("tags") or [],
                        embedding=vector,
                    )
                )

            doc.chunk_count = len(records)
            doc.status = "completed"
            await db.commit()
            logger.info(
                "document_processed",
                doc_id=str(doc.id),
                kb_id=str(doc.kb_id),
                chunk_count=len(records),
            )
            return doc
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            doc = await db.get(Document, doc_id)
            if doc is not None:
                doc.status = "failed"
                doc.error_message = str(exc)[:500]
                await db.commit()
            logger.exception(
                "document_process_failed", doc_id=str(doc_id), error=str(exc)[:500]
            )
            return doc

