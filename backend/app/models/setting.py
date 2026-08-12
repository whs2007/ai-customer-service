"""系统配置模型（08 §5.2 settings 表）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True, comment="配置键")
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="配置值")
    group: Mapped[str] = mapped_column(String(50), nullable=False, comment="分组")
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

