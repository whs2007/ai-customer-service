"""模型配置模型（08 §5.2 model_profiles 表；完整管理 UI 见 B6 系统设置）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (
        CheckConstraint(
            "role IN ('chat','embedding','rerank')", name="ck_model_profiles_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="配置名称"
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False, comment="提供商")
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型名")
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_enc: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", comment="加密存储的 API Key（B6 加密）"
    )
    temperature: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("0.7")
    )
    top_p: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("0.9")
    )
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="chat", comment="chat/embedding/rerank"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

