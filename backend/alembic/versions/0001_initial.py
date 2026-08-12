"""B1 初始迁移：pgvector 扩展 + users + audit_logs + 默认管理员。

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-12
"""

from __future__ import annotations

from typing import Sequence, Union

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 本地开发默认管理员（仅 dev；生产环境应由初始化流程创建并修改密码）
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_DISPLAY_NAME = "管理员"


def upgrade() -> None:
    # pgvector 扩展（08 §2：向量存储已确认 pgvector）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=50), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("role IN ('admin','agent','viewer')", name="ck_users_role"),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_users_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column("ip", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # 种子默认管理员（幂等）
    password_hash = bcrypt.hashpw(
        DEFAULT_ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    op.execute(
        sa.text(
            """
            INSERT INTO users (id, username, password_hash, display_name, role, status)
            VALUES (gen_random_uuid(), :username, :pwd, :display, 'admin', 'active')
            ON CONFLICT (username) DO NOTHING
            """
        ).bindparams(
            username=DEFAULT_ADMIN_USERNAME,
            pwd=password_hash,
            display=DEFAULT_ADMIN_DISPLAY_NAME,
        )
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("users")
    # 注意：vector 扩展为集群级对象，降级时不做删除，避免影响其他库

