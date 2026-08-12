"""评测集候选模型（【新增】08 §5.2 未含：引用反馈/标注回流 → 候选 → 管理员确认入集）。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalCandidateStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EvalCandidate(Base):
    __tablename__ = "eval_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','confirmed','rejected')",
            name="ck_eval_candidates_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="feedback", comment="feedback/annotation"
    )
    source_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="来源记录 ID（feedback/session）"
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EvalCandidateStatus.PENDING.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

