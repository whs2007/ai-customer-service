"""B3 检索：chunks 增加 tsvector 全文检索生成列与 GIN 索引。

Revision ID: 0003_retrieval
Revises: 0002_knowledge_base
Create Date: 2026-08-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "0003_retrieval"
down_revision: Union[str, None] = "0002_knowledge_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "search_vector",
            TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(question, '') || ' ' || coalesce(answer, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    # GIN 索引加速全文检索（08 §5.3 建议）
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_search_vector "
        "ON chunks USING gin (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_vector")
    op.drop_column("chunks", "search_vector")

