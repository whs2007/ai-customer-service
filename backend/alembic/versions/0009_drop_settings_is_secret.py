"""清理：移除从未启用的 settings.is_secret 字段（死配置）。

Revision ID: 0009_drop_settings_is_secret
Revises: 0008_token_security
Create Date: 2026-08-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_drop_settings_is_secret"
down_revision: Union[str, None] = "0008_token_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("settings", "is_secret")


def downgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
