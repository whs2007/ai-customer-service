"""渠道配置模型（11 §8 / 开发文档 01 §8.6 channel_configs）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChannelConfig(Base):
    """渠道 → 默认知识库 / 是否允许转人工 / 营业时间。"""

    __tablename__ = "channel_configs"

    channel: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="渠道标识（如 web_user）"
    )
    default_kb_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, comment="默认知识库 ID 列表"
    )
    allow_human: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    business_hours: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="营业时间（二期用）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
