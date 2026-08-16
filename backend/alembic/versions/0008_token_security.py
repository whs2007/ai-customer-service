"""会话安全：users.token_version + refresh_tokens 表（服务端吊销）。

背景：原实现 refresh token 轮换无服务端登记，改密/停用后旧 token 仍有效。
本迁移：
- users 增加 token_version（改密/停用/角色变更时 +1，JWT 立即失效）；
- 新增 refresh_tokens 表（jti 服务端登记，支持轮换复用检测与吊销）。

Revision ID: 0008_token_security
Revises: 0007_admin_seed_safety
Create Date: 2026-08-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008_token_security"
down_revision: Union[str, None] = "0007_admin_seed_safety"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="会话版本号：改密/停用/角色变更时 +1，旧 JWT 全部失效",
        ),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(length=64), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_column("users", "token_version")
