"""认证业务逻辑：登录校验、令牌签发、审计。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User, UserStatus
from app.schemas.auth import TokenPair
from app.services.audit_service import write_audit


async def authenticate_user(
    db: AsyncSession, username: str, password: str, ip: str | None = None
) -> tuple[User, TokenPair]:
    """校验账密并签发令牌；登录成功/失败均写审计日志。"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        await write_audit(
            db,
            user_id=user.id if user else None,
            action="login_failed",
            target_type="user",
            ip=ip,
            detail={"username": username},
        )
        raise UnauthorizedError("用户名或密码错误")

    if user.status != UserStatus.ACTIVE.value:
        await write_audit(
            db,
            user_id=user.id,
            action="login_failed",
            target_type="user",
            ip=ip,
            detail={"username": username, "reason": "disabled"},
        )
        raise UnauthorizedError("账号已停用，请联系管理员")

    user.last_login_at = datetime.now(timezone.utc)
    tokens = issue_tokens(user)
    await write_audit(
        db,
        user_id=user.id,
        action="login",
        target_type="user",
        ip=ip,
        detail={"username": username},
    )
    await db.commit()
    return user, tokens


def issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id), user.role),
    )


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenPair:
    """刷新令牌（轮换：旧 refresh 换发新的 access+refresh）。"""
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("无效的登录凭证")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedError("账号不可用，请重新登录")

    return issue_tokens(user)
