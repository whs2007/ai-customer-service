"""Chunk 切片模型（08 §5.2 chunks 表）。

【新增】category：承载 FAQ 模板"分类"列（08 表结构无此列，04 §4.6 模板已含分类）。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.config import get_settings


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="冗余，检索过滤用",
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="序号")
    question: Mapped[str] = mapped_column(String(200), nullable=False, comment="问题")
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment="答案/内容")
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="分类（FAQ 模板可选列）"
    )
    page: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="页码/来源")
    row: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="行号")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="字数")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, comment="标签列表")
    embedding: Mapped[list | None] = mapped_column(
        Vector(get_settings().embedding_dim), nullable=True, comment="向量（bge-m3 1024 维）"
    )
    # 全文检索向量（08 §4.3 变更：tsvector 混合检索；'simple' 配置 + 中文 bigram 查询）
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(question, '') || ' ' || coalesce(answer, ''))",
            persisted=True,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
