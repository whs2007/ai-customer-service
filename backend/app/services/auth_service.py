"""认证业务逻辑：登录校验、令牌签发、轮换与吊销、审计。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, ConflictError, UnauthorizedError
from app.core.ratelimit import verify_captcha
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    validate_username,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import Role, User, UserStatus
from app.schemas.auth import RegisterRequest, TokenPair
from app.services.audit_service import write_audit
from app.services.token_security import (
    persist_refresh_token,
    revoke_refresh_token,
)


async def authenticate_user(
    db: AsyncSession, username: str, password: str, ip: str | None = None
) -> tuple[User, TokenPair]:
    """校验账密并签发令牌；登录失败连续 N 次锁定（11 §3.3 / 12 §2.2）。"""
    settings = get_settings()
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        await write_audit(
            db,
            user_id=None,
            action="login_failed",
            target_type="user",
            ip=ip,
            detail={"username": username},
        )
        raise UnauthorizedError("用户名或密码错误")

    now = datetime.now(UTC)
    if user.locked_until is not None and user.locked_until > now:
        remain_min = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        await write_audit(
            db,
            user_id=str(user.id),
            action="login_failed",
            target_type="user",
            ip=ip,
            detail={"username": username, "reason": "locked"},
        )
        await db.commit()
        raise UnauthorizedError(f"登录失败次数过多，账号已锁定，请 {remain_min} 分钟后再试")

    if user.status != UserStatus.ACTIVE.value:
        await write_audit(
            db,
            user_id=str(user.id),
            action="login_failed",
            target_type="user",
            ip=ip,
            detail={"username": username, "reason": "disabled"},
        )
        raise UnauthorizedError("账号已停用，请联系管理员")

    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.login_failed_lock_threshold:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_count = 0
            await write_audit(
                db,
                user_id=str(user.id),
                action="login_failed",
                target_type="user",
                ip=ip,
                detail={
                    "username": username,
                    "reason": "locked",
                    "lock_minutes": settings.login_lock_minutes,
                },
            )
            await db.commit()
            raise UnauthorizedError(
                f"连续 {settings.login_failed_lock_threshold} 次密码错误，"
                f"账号已锁定 {settings.login_lock_minutes} 分钟"
            )
        await write_audit(
            db,
            user_id=str(user.id),
            action="login_failed",
            target_type="user",
            ip=ip,
            detail={"username": username, "failed_count": user.failed_login_count},
        )
        await db.commit()
        raise UnauthorizedError("用户名或密码错误")

    user.last_login_at = now
    user.failed_login_count = 0
    user.locked_until = None
    tokens = await _issue_tokens(db, user)
    await write_audit(
        db,
        user_id=str(user.id),
        action="login",
        target_type="user",
        ip=ip,
        detail={"username": username},
    )
    await db.commit()
    return user, tokens


async def register_user(
    db: AsyncSession, payload: RegisterRequest, ip: str | None = None
) -> tuple[User, TokenPair]:
    """用户端自助注册（12 §2.1）：校验规则 + 验证码 → 建 user 账号 → 自动登录。"""
    username = payload.username.strip()
    username_err = validate_username(username)
    if username_err:
        raise BadRequestError(username_err)
    password_err = validate_password_strength(payload.password)
    if password_err:
        raise BadRequestError(password_err)
    if payload.password != payload.confirm_password:
        raise BadRequestError("两次输入的密码不一致")
    verify_captcha(payload.captcha_id, payload.captcha)

    existing = await db.scalar(select(User).where(User.username == username))
    if existing is not None:
        raise ConflictError("用户名已存在")
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=(payload.display_name or username).strip()[:50],
        role=Role.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    try:
        # 【修复 M3】并发同名注册：唯一约束冲突转 409，而不是 500
        await db.flush()
        tokens = await _issue_tokens(db, user)
        await write_audit(
            db,
            user_id=str(user.id),
            action="register",
            target_type="user",
            target_id=str(user.id),
            ip=ip,
            detail={"username": username},
        )
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise ConflictError("用户名已存在") from None
    return user, tokens


async def change_password(
    db: AsyncSession, user: User, old_password: str, new_password: str
) -> User:
    """用户端修改密码：校验旧密码 → 更新哈希 → token_version + 1（旧 token 全失效）。"""
    if not verify_password(old_password, user.password_hash):
        raise BadRequestError("旧密码不正确")
    password_err = validate_password_strength(new_password)
    if password_err:
        raise BadRequestError(password_err)
    if old_password == new_password:
        raise BadRequestError("新密码不能与旧密码相同")
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    await write_audit(
        db,
        user_id=str(user.id),
        action="password_change",
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username},
    )
    await db.commit()
    await db.refresh(user)
    return user


async def _issue_tokens(db: AsyncSession, user: User) -> TokenPair:
    """签发 access + refresh 并登记 refresh token（服务端可吊销）。"""
    version = user.token_version
    jti = str(uuid.uuid4())
    pair = TokenPair(
        access_token=create_access_token(
            str(user.id), user.role, version=version
        ),
        refresh_token=create_refresh_token(
            str(user.id), user.role, version=version, jti=jti
        ),
    )
    expires_at = datetime.now(UTC) + timedelta(
        days=get_settings().refresh_token_expire_days
    )
    await persist_refresh_token(db, jti, user.id, expires_at)
    return pair


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenPair:
    """刷新令牌（轮换：旧 jti 吊销换发新对；复用/已吊销/版本不匹配一律拒绝）。"""
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("无效的登录凭证")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedError("账号不可用，请重新登录")

    if payload.get("ver") != user.token_version:
        raise UnauthorizedError("登录状态已失效，请重新登录")

    jti = payload.get("jti")
    if not jti:
        raise UnauthorizedError("无效的登录凭证")
    stored = await db.get(RefreshToken, jti)
    if stored is None or stored.revoked_at is not None:
        # 轮换后旧 refresh 再次使用（或已被吊销）→ 拒绝
        raise UnauthorizedError("登录凭证已失效，请重新登录")
    if stored.expires_at is not None and stored.expires_at < datetime.now(
        UTC
    ):
        await revoke_refresh_token(db, jti)
        await db.commit()
        raise UnauthorizedError("登录凭证已过期，请重新登录")

    await revoke_refresh_token(db, jti)
    tokens = await _issue_tokens(db, user)
    await db.commit()
    return tokens
