"""评测集模型（08 §5.2 eval_sets 表）。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalSetSource(str, enum.Enum):
    MANUAL = "manual"
    PUBLIC = "public"
    FEEDBACK = "feedback"


class EvalSet(Base):
    __tablename__ = "eval_sets"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual','public','feedback')", name="ck_eval_sets_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="名称（唯一）"
    )
    description: Mapped[str] = mapped_column(
        String(200), nullable=False, default=""
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EvalSetSource.MANUAL.value
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

