"""会话模型（08 §5.2 sessions 表）。

【新增】escalation_count：连续兜底次数（08 §4.4 转人工规则 escalation_count ≥ 2）。
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    TRANSFERRED = "transferred"


class ChatSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','closed','transferred')", name="ck_sessions_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(
        String(50), nullable=False, default="web", comment="来源渠道"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SessionStatus.ACTIVE.value
    )
    kb_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="知识库 ID 列表（多库检索）"
    )
    escalation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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

