"""评测任务模型（08 §5.2 eval_tasks 表）。

【新增】kb_ids：评测逐条检索使用的知识库列表（09 未指明，实施补充）。
【新增】error_message：任务失败原因（供失败重试提示）。
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalTaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvalTask(Base):
    __tablename__ = "eval_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_eval_tasks_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    eval_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    kb_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EvalTaskStatus.PENDING.value
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_avg: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment="平均分（百分比）"
    )
    metrics: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="分指标得分 accuracy/relevancy/semantic"
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="失败原因"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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

