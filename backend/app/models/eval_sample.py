"""评测样本模型（08 §5.2 eval_samples 表）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalSample(Base):
    __tablename__ = "eval_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    eval_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False, comment="问题")
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False, comment="期望答案")
    expected_chunks: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="期望引用的 Chunk ID 列表"
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual", comment="manual/public/feedback"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

