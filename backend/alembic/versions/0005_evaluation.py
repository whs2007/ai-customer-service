"""B4.5 应用评测：eval_sets / eval_samples / eval_tasks / eval_results / eval_candidates。

串联在并发的 0005_ticket_kb_visibility（工单命中片段 + 知识库可见性）之后。

Revision ID: 0005_evaluation
Revises: 0004_chat
Create Date: 2026-08-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0005_evaluation"
down_revision: Union[str, None] = "0005_ticket_kb_visibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_sets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint(
            "source IN ('manual','public','feedback')", name="ck_eval_sets_source"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "eval_samples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("eval_set_id", UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("expected_chunks", JSONB(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["eval_set_id"], ["eval_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_samples_eval_set_id", "eval_samples", ["eval_set_id"])

    op.create_table(
        "eval_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("eval_set_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_profile_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kb_ids", JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_avg", sa.Numeric(6, 2), nullable=True),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_eval_tasks_status",
        ),
        sa.ForeignKeyConstraint(["eval_set_id"], ["eval_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["model_profile_id"], ["model_profiles.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_tasks_eval_set_id", "eval_tasks", ["eval_set_id"])
    op.create_index("ix_eval_tasks_status", "eval_tasks", ["status"])

    op.create_table(
        "eval_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sample_id", UUID(as_uuid=True), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("citations", JSONB(), nullable=False),
        sa.Column("scores", JSONB(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["eval_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sample_id"], ["eval_samples.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_results_task_id", "eval_results", ["task_id"])

    op.create_table(
        "eval_candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="feedback"),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','rejected')",
            name="ck_eval_candidates_status",
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("eval_candidates")
    op.drop_table("eval_results")
    op.drop_table("eval_tasks")
    op.drop_table("eval_samples")
    op.drop_table("eval_sets")
