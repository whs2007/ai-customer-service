"""每日统计模型（08 §5.2 dashboard_stats 表；B5 按需计算 + 进程内缓存，落表供后续定时聚合）。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DashboardStat(Base):
    __tablename__ = "dashboard_stats"

    stat_date: Mapped[date] = mapped_column(Date, primary_key=True, comment="统计日期")
    sessions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_solved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_solved_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    transfer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kb_hit_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    intent_distribution: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, comment="意图分布"
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

