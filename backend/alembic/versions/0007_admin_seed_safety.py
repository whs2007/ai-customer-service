"""安全加固：移除仍使用默认口令的种子管理员（B6b 遗留风险）。

背景：0001 迁移曾在升级时创建 admin/admin123。此迁移仅当该账号
密码仍匹配默认口令 admin123 时删除（已改密的账号不受影响），
初始管理员改由 `python -m app.cli bootstrap` 引导创建。

Revision ID: 0007_admin_seed_safety
Revises: 0006_operations
Create Date: 2026-08-13
"""

from __future__ import annotations

from typing import Sequence, Union

import bcrypt
import sqlalchemy as sa
from alembic import op

revision: str = "0007_admin_seed_safety"
down_revision: Union[str, None] = "0006_operations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SEED_PASSWORD = "admin123"


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, password_hash FROM users "
            "WHERE username = 'admin' AND status = 'active'"
        )
    ).fetchall()
    removed = 0
    for user_id, password_hash in rows:
        try:
            if bcrypt.checkpw(
                DEFAULT_SEED_PASSWORD.encode("utf-8"), password_hash.encode("utf-8")
            ):
                conn.execute(
                    sa.text("DELETE FROM users WHERE id = :uid"), {"uid": user_id}
                )
                removed += 1
        except ValueError:
            # 哈希格式异常：不误删，交由人工处理
            continue
    if removed:
        print(f"[migrate] 已移除 {removed} 个仍使用默认口令的种子管理员，"
              "请通过 python -m app.cli bootstrap 创建新管理员")


def downgrade() -> None:
    # 数据迁移不可逆（不重建已知口令账号），降级为空操作
    pass
