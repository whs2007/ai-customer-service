"""工单模型（08 §5.2 tickets 表；列表页 B5 实现）。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    PROCESSING = "processing"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','processing','closed')", name="ck_tickets_status"
        ),
        CheckConstraint("priority IN ('high','medium','low')", name="ck_tickets_priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_no: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True, comment="编号 TK+时间戳+随机"
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="human_service"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="诉求内容")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TicketStatus.OPEN.value
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TicketPriority.MEDIUM.value
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
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

