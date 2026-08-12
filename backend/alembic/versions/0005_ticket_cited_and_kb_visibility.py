"""0005 工单命中片段 + 知识库资源级可见性（08 §4.5 / 00 §3 新增）。

Revision ID: 0005_ticket_kb_visibility
Revises: 0004_chat
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_ticket_kb_visibility"
down_revision: str = "0004_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "cited_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="知识库命中片段 ID 列表（08 §4.5 新增）",
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "visibility",
            sa.String(length=20),
            server_default="all",
            nullable=False,
            comment="可见范围：all/role/user",
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "visible_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "visible_user_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "visible_user_ids")
    op.drop_column("knowledge_bases", "visible_roles")
    op.drop_column("knowledge_bases", "visibility")
    op.drop_column("tickets", "cited_chunk_ids")
