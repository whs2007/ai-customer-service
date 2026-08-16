"""向量与关键词检索（08 §4.3）。"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import ARRAY, String, cast, func, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document


async def vector_search(
    db: AsyncSession,
    kb_ids: list[uuid.UUID],
    query_vector: list[float],
    tags: list[str],
    limit: int,
) -> list[dict]:
    """pgvector 余弦相似度检索（08 §4.3：必须携带 kb_ids 过滤）。"""
    stmt = (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.kb_id,
            Document.file_name.label("document_name"),
            Chunk.page,
            Chunk.row,
            Chunk.question,
            Chunk.answer,
            (1 - Chunk.embedding.cosine_distance(query_vector)).label("similarity"),
        )
        .join(Document, Document.id == Chunk.doc_id)
        .where(
            Chunk.kb_id.in_(kb_ids),
            Chunk.embedding.is_not(None),
            Document.deleted_at.is_(None),
        )
        .order_by(Chunk.embedding.cosine_distance(query_vector).asc())
        .limit(limit)
    )
    if tags:
        # JSONB 数组 ?| text[]：标签取交集（08 §4.3 新增）
        stmt = stmt.where(Chunk.tags.op("?|")(cast(array(tags), ARRAY(String))))
    rows = (await db.execute(stmt)).all()
    return [dict(row._mapping) for row in rows]


def build_cjk_tsquery(query: str, max_terms: int = 40) -> str | None:
    """中文查询转字符 bigram 的 tsquery（OR 聚合）。

    【建议】'simple' 配置无中文分词，bigram 是工程折中；生产可换 zhparser/pg_jieba。
    非中文查询返回 None，由调用方改用 plainto_tsquery。
    """
    chars = re.findall(r"[\u4e00-\u9fff]", query)
    if not chars:
        return None
    grams = set(chars)
    grams.update(f"{a}{b}" for a, b in zip(chars, chars[1:], strict=False))
    return " | ".join(sorted(grams)[:max_terms])


async def keyword_search(
    db: AsyncSession,
    kb_ids: list[uuid.UUID],
    query: str,
    tags: list[str],
    limit: int,
) -> list[dict]:
    """PostgreSQL 全文检索（tsvector，08 §4.3 变更），按 ts_rank 取候选。"""
    tq = build_cjk_tsquery(query)
    tsq = (
        func.plainto_tsquery("simple", query)
        if tq is None
        else func.to_tsquery("simple", tq)
    )

    stmt = (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.kb_id,
            Document.file_name.label("document_name"),
            Chunk.page,
            Chunk.row,
            Chunk.question,
            Chunk.answer,
            func.ts_rank(Chunk.search_vector, tsq).label("kw_score"),
        )
        .join(Document, Document.id == Chunk.doc_id)
        .where(
            Chunk.kb_id.in_(kb_ids),
            Document.deleted_at.is_(None),
            Chunk.search_vector.op("@@")(tsq),
        )
        .order_by(func.ts_rank(Chunk.search_vector, tsq).desc())
        .limit(limit)
    )
    if tags:
        stmt = stmt.where(Chunk.tags.op("?|")(cast(array(tags), ARRAY(String))))
    rows = (await db.execute(stmt)).all()
    return [dict(row._mapping) for row in rows]
