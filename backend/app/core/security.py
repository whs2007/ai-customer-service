"""JWT 签发/校验、密码哈希与密钥加解密（08 §4.1 / §7 / §8）。"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import TokenExpiredError, UnauthorizedError

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def hash_password(password: str) -> str:
    """bcrypt 哈希。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _create_token(
    user_id: str,
    role: str,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        role,
        TOKEN_TYPE_ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str, role: str) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        role,
        TOKEN_TYPE_REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """校验 JWT；过期抛 TokenExpiredError，其他异常抛 UnauthorizedError。"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("无效的登录凭证") from exc

    if expected_type and payload.get("type") != expected_type:
        raise UnauthorizedError("登录凭证类型不匹配")
    return payload


def _xor_key() -> bytes:
    secret = get_settings().jwt_secret.encode("utf-8")
    return hashlib.sha256(secret).digest()


def encrypt_secret(plain: str) -> str:
    """密钥加密：XOR + Base64（08 §4.7 API Key 加密存储）。

    【说明】轻量混淆（标准库实现，无额外依赖）；正式加密（Fernet/KMS）按文档规划留 B6。
    """
    if not plain:
        return ""
    key = _xor_key()
    data = plain.encode("utf-8")
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(out).decode("ascii")


def decrypt_secret(enc: str) -> str:
    """密钥解密：Base64 + XOR。非法密文返回空串（避免崩溃）。"""
    if not enc:
        return ""
    try:
        data = base64.urlsafe_b64decode(enc.encode("ascii"))
    except Exception:  # noqa: BLE001
        return ""
    key = _xor_key()
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return out.decode("utf-8", errors="ignore")
