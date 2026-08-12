"""B5 运营闭环：ticket_notes / dashboard_stats / session_annotations 三表。

Revision ID: 0006_operations
Revises: 0005_evaluation
Create Date: 2026-08-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0006_operations"
down_revision: Union[str, None] = "0005_evaluation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", UUID(as_uuid=True), nullable=False),
        sa.Column("operator_id", UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("status_from", sa.String(length=20), nullable=True),
        sa.Column("status_to", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_notes_ticket_id", "ticket_notes", ["ticket_id"])

    op.create_table(
        "dashboard_stats",
        sa.Column("stat_date", sa.Date(), primary_key=True),
        sa.Column("sessions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_solved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_solved_rate", sa.Numeric(6, 2), nullable=True),
        sa.Column("transfer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kb_hit_rate", sa.Numeric(6, 2), nullable=True),
        sa.Column("intent_distribution", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "session_annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tags", JSONB(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("include_in_eval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("eval_set_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["eval_set_id"], ["eval_sets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("ix_session_annotations_session_id", "session_annotations", ["session_id"])


def downgrade() -> None:
    op.drop_table("session_annotations")
    op.drop_table("dashboard_stats")
    op.drop_table("ticket_notes")

