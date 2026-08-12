"""检索测试请求/响应（08 §6.2 / 05 §4）。"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.knowledge import _clean_tags

RetrieverMode = Literal["vector", "hybrid", "hybrid_rerank"]


class RetrievalRequest(BaseModel):
    kb_ids: list[uuid.UUID] = Field(min_length=1, max_length=20, description="知识库 ID 列表（多库）")
    query: str = Field(min_length=1, max_length=200, description="查询问题")
    top_k: int = Field(default=3, ge=1, le=10, description="TopK（1–10，默认 3）")
    tags: list[str] = Field(default_factory=list, max_length=10, description="标签过滤")
    retriever_mode: RetrieverMode = Field(default="hybrid", description="检索方式")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return _clean_tags(v)


class RetrievalHit(BaseModel):
    chunk_id: uuid.UUID
    kb_id: uuid.UUID
    document_name: str
    page: str | None = None
    row: str | None = None
    question: str
    answer: str
    retrieval_score: float
    rerank_score: float | None = None


class RetrievalResponse(BaseModel):
    query: str
    top_k: int
    retriever_mode: RetrieverMode
    actual_mode: RetrieverMode
    rerank_skipped: bool = False
    hits: list[RetrievalHit]


class RetrievalCandidatesRequest(BaseModel):
    """补充引用候选（03 §4.4：从候选片段中选择，08 §6.2 新增）。"""

    kb_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=1, max_length=200)
    top_n: int = Field(default=20, ge=1, le=50, description="候选数量")
