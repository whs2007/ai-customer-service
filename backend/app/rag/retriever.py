"""检索编排：向量 + 关键词 RRF 融合 → 归一化 → 可选重排（08 §4.3）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.models.knowledge_base import KnowledgeBase
from app.models.user import Role, User
from app.rag.embeddings import EmbeddingClient
from app.rag.reranker import RerankClient
from app.rag.vector_store import keyword_search, vector_search

RRF_K = 60  # RRF 常数（08 §4.3）
RERANK_TOP_N = 20  # 重排候选数（建议 20）


async def filter_accessible_kb_ids(
    db: AsyncSession, requested: list[uuid.UUID], user: User | None = None
) -> list[uuid.UUID]:
    """逐库权限校验（08 §8 数据隔离 / 00 §3 资源级权限）。

    admin 与未传用户：仅校验存在；agent/viewer：按知识库可见范围
    （all / role / user）过滤。
    """
    result = await db.execute(
        select(
            KnowledgeBase.id,
            KnowledgeBase.visibility,
            KnowledgeBase.visible_roles,
            KnowledgeBase.visible_user_ids,
        ).where(
            KnowledgeBase.id.in_(requested), KnowledgeBase.deleted_at.is_(None)
        )
    )
    accessible: list[uuid.UUID] = []
    for kb_id, visibility, visible_roles, visible_user_ids in result.all():
        if user is None or user.role == Role.ADMIN.value or visibility == "all":
            accessible.append(kb_id)
        elif visibility == "role" and user.role in (visible_roles or []):
            accessible.append(kb_id)
        elif visibility == "user" and str(user.id) in [
            str(x) for x in (visible_user_ids or [])
        ]:
            accessible.append(kb_id)
    return accessible


def _rrf_fuse(vector_rows: list[dict], keyword_rows: list[dict]) -> list[dict]:
    """RRF 融合：score = Σ 1/(K + rank)。"""
    merged: dict[uuid.UUID, dict] = {}
    for rows in (vector_rows, keyword_rows):
        for rank, row in enumerate(rows, start=1):
            chunk_id = row["chunk_id"]
            entry = merged.setdefault(chunk_id, dict(row))
            entry["_rrf"] = entry.get("_rrf", 0.0) + 1.0 / (RRF_K + rank)
    return list(merged.values())


def _normalize_minmax(entries: list[dict], key: str) -> None:
    """min-max 归一化到 0–100（08 §4.3：检索分归一化）。"""
    if not entries:
        return
    values = [entry[key] for entry in entries]
    lo, hi = min(values), max(values)
    if hi == lo:
        for entry in entries:
            entry["retrieval_score"] = 100.0
        return
    for entry in entries:
        entry["retrieval_score"] = round(
            (entry[key] - lo) * 100.0 / (hi - lo), 1
        )


async def run_retrieval_test(
    db: AsyncSession,
    kb_ids,
    query,
    top_k,
    tags,
    retriever_mode,
    user: User | None = None,
) -> dict:
    """检索测试主流程，返回 hits 与生效模式。"""
    accessible = await filter_accessible_kb_ids(db, kb_ids, user)
    if not accessible:
        raise BadRequestError("所选知识库无效或无权限")

    query_vec = await EmbeddingClient(get_settings()).embed_text(query)
    pool_size = max(top_k, RERANK_TOP_N)
    vector_rows = await vector_search(db, accessible, query_vec, tags, pool_size)

    actual_mode = retriever_mode
    rerank_skipped = False

    if retriever_mode == "vector":
        _normalize_minmax(vector_rows, "similarity")
        vector_rows.sort(key=lambda r: r["retrieval_score"], reverse=True)
        hits = vector_rows[:top_k]
    else:
        keyword_rows = await keyword_search(db, accessible, query, tags, pool_size)
        fused = _rrf_fuse(vector_rows, keyword_rows)
        if not fused:
            hits = []
        else:
            _normalize_minmax(fused, "_rrf")
            if retriever_mode == "hybrid_rerank":
                client = RerankClient(get_settings())
                if client.available:
                    candidates = fused[:RERANK_TOP_N]
                    scores = await client.rerank(
                        query,
                        [f"{c['question']}\n{c['answer']}" for c in candidates],
                        top_n=len(candidates),
                    )
                    for candidate, score in zip(candidates, scores):
                        candidate["rerank_score"] = round(score, 4)
                    candidates.sort(key=lambda c: c.get("rerank_score") or 0.0, reverse=True)
                    fused = candidates
                else:
                    actual_mode = "hybrid"
                    rerank_skipped = True
                    fused.sort(key=lambda r: r["retrieval_score"], reverse=True)
            else:
                fused.sort(key=lambda r: r["retrieval_score"], reverse=True)
            hits = fused[:top_k]

    return {
        "query": query,
        "top_k": top_k,
        "retriever_mode": retriever_mode,
        "actual_mode": actual_mode,
        "rerank_skipped": rerank_skipped,
        "hits": hits,
    }
