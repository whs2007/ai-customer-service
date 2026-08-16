"""用户端 + 客服工作台（P0+P1：角色扩展、登录锁定、工单时间、三张新表）。

Revision ID: 0010_user_side_workbench
Revises: 0009_drop_settings_is_secret
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_user_side_workbench"
down_revision: Union[str, None] = "0009_drop_settings_is_secret"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- users：角色约束加 user；新增登录失败风控字段 ----
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin','agent','viewer','user')",
    )
    op.add_column(
        "users",
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )

    # ---- messages：角色约束加 agent（人工客服回复） ----
    op.drop_constraint("ck_messages_role", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_role",
        "messages",
        "role IN ('user','assistant','agent','system')",
    )

    # ---- tickets：认领/关闭时间与关闭原因 ----
    op.add_column(
        "tickets", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("close_reason", sa.String(length=200), nullable=True)
    )

    # ---- session_reads：各端已读游标 ----
    op.create_table(
        "session_reads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reader_role", sa.String(length=20), nullable=False),
        sa.Column(
            "reader_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "last_read_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "session_id", "reader_role", "reader_id", name="uq_session_read_reader"
        ),
    )
    op.create_index(
        "ix_session_reads_session_id", "session_reads", ["session_id"]
    )

    # ---- ticket_ratings：工单满意度评价（ticket 唯一） ----
    op.create_table(
        "ticket_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("ticket_id", name="uq_ticket_ratings_ticket"),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_ticket_ratings_score"),
    )

    # ---- channel_configs：渠道默认知识库等 ----
    op.create_table(
        "channel_configs",
        sa.Column("channel", sa.String(length=50), primary_key=True),
        sa.Column(
            "default_kb_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "allow_human",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("business_hours", postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("channel_configs")
    op.drop_table("ticket_ratings")
    op.drop_table("session_reads")
    op.drop_column("tickets", "close_reason")
    op.drop_column("tickets", "closed_at")
    op.drop_column("tickets", "claimed_at")
    op.drop_constraint("ck_messages_role", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_role",
        "messages",
        "role IN ('user','assistant','system')",
    )
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin','agent','viewer')",
    )
