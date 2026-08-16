"""客服工作台/用户端常用查询索引（审计 M1）。

Revision ID: 0011_workbench_indexes
Revises: 0010_user_side_workbench
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0011_workbench_indexes"
down_revision: Union[str, None] = "0010_user_side_workbench"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 我的会话：WHERE user_id
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    # 我的工单：WHERE user_id
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])
    # 我负责的队列：WHERE assignee_id
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])


def downgrade() -> None:
    op.drop_index("ix_tickets_assignee_id", table_name="tickets")
    op.drop_index("ix_tickets_user_id", table_name="tickets")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
