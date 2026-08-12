"""Chunk 业务逻辑（04 §4）：列表、新增、编辑（重新向量化）、删除。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.models.chunk import Chunk
from app.models.document import Document
from app.rag.embeddings import EmbeddingClient
from app.schemas.knowledge import ChunkCreate, ChunkUpdate


async def list_chunks(
    db: AsyncSession,
    doc_id: uuid.UUID,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Chunk], int]:
    total = (
        await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.doc_id == doc_id))
        or 0
    )
    result = await db.execute(
        select(Chunk)
        .where(Chunk.doc_id == doc_id)
        .order_by(Chunk.chunk_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_chunk(db: AsyncSession, chunk_id: uuid.UUID) -> Chunk:
    chunk = await db.get(Chunk, chunk_id)
    if chunk is None:
        raise NotFoundError("Chunk 不存在")
    return chunk


async def _next_index(db: AsyncSession, doc_id: uuid.UUID) -> int:
    max_index = await db.scalar(
        select(func.max(Chunk.chunk_index)).where(Chunk.doc_id == doc_id)
    )
    return (max_index or 0) + 1


async def create_chunk(db: AsyncSession, payload: ChunkCreate) -> Chunk:
    doc = await db.get(Document, payload.doc_id)
    if doc is None:
        raise NotFoundError("文档不存在")
    embedding = await EmbeddingClient(get_settings()).embed_text(payload.question.strip())
    chunk = Chunk(
        doc_id=payload.doc_id,
        kb_id=doc.kb_id,
        chunk_index=await _next_index(db, payload.doc_id),
        question=payload.question.strip(),
        answer=payload.answer.strip(),
        category=payload.category,
        tags=payload.tags,
        page=payload.page,
        row=payload.row,
        word_count=len(payload.answer.strip()),
        embedding=embedding,
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    doc.chunk_count += 1
    await db.commit()
    return chunk


async def update_chunk(db: AsyncSession, chunk_id: uuid.UUID, payload: ChunkUpdate) -> Chunk:
    chunk = await get_chunk(db, chunk_id)
    changed = False
    if payload.question is not None and payload.question.strip() != chunk.question:
        chunk.question = payload.question.strip()
        changed = True
    if payload.answer is not None and payload.answer.strip() != chunk.answer:
        chunk.answer = payload.answer.strip()
        chunk.word_count = len(chunk.answer)
        changed = True
    if payload.category is not None:
        chunk.category = payload.category or None
        changed = True
    if payload.tags is not None:
        chunk.tags = payload.tags
        changed = True
    if payload.page is not None:
        chunk.page = payload.page or None
        changed = True
    if payload.row is not None:
        chunk.row = payload.row or None
        changed = True

    if changed:
        # 编辑后仅重算该条向量（08 §4.2：更新文本后仅重算该条向量）
        chunk.embedding = await EmbeddingClient(get_settings()).embed_text(chunk.question)
        await db.commit()
        await db.refresh(chunk)
    return chunk


async def delete_chunk(db: AsyncSession, chunk_id: uuid.UUID) -> None:
    chunk = await get_chunk(db, chunk_id)
    doc_id = chunk.doc_id
    await db.delete(chunk)
    doc = await db.get(Document, doc_id)
    if doc is not None:
        doc.chunk_count = max(0, doc.chunk_count - 1)
    await db.commit()

