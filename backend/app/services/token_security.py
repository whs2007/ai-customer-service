"""会话令牌安全服务（08 §8）：
- refresh token 服务端登记（登录时写入，刷新时吊销旧 jti，支持轮换复用检测）；
- 用户会话版本号（token_version）：改密/停用/角色变更时 +1，全部 JWT 立即失效。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User


async def persist_refresh_token(
    db: AsyncSession, jti: str, user_id: uuid.UUID, expires_at: datetime
) -> None:
    """登录/刷新后登记 refresh token（幂等 upsert）。"""
    existing = await db.get(RefreshToken, jti)
    if existing is None:
        db.add(
            RefreshToken(
                jti=jti,
                user_id=user_id,
                expires_at=expires_at,
            )
        )
    else:
        existing.expires_at = expires_at
        existing.revoked_at = None


async def revoke_refresh_token(db: AsyncSession, jti: str) -> None:
    token = await db.get(RefreshToken, jti)
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    """吊销用户全部会话：token_version +1 + refresh 全部作废。"""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(token_version=User.token_version + 1)
    )
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )


def expires_at_from_payload(payload: dict) -> datetime:
    """从 JWT exp 声明转 datetime（UTC）。"""
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        return datetime.fromtimestamp(exp, tz=UTC)
    return datetime.now(UTC)
