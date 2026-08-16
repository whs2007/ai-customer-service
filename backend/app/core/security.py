"""JWT 签发/校验、密码哈希与密钥加解密（08 §4.1 / §7 / §8）。"""

from __future__ import annotations

import base64
import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

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


def validate_username(username: str) -> str | None:
    """用户端注册用户名规则（开发文档 01 §2.1）：4~32 位，字母/数字/下划线/中文。"""
    if not username or not (4 <= len(username) <= 32):
        return "用户名长度需为 4~32 位"
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fa5]+", username):
        return "用户名仅支持字母、数字、下划线与中文"
    return None


def validate_password_strength(password: str) -> str | None:
    """用户端注册/改密密码规则：8~64 位，至少包含字母和数字。"""
    if not password or not (8 <= len(password) <= 64):
        return "密码长度需为 8~64 位"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "密码需同时包含字母和数字"
    return None


def _create_token(
    user_id: str,
    role: str,
    token_type: str,
    expires_delta: timedelta,
    version: int = 0,
    jti: str | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "type": token_type,
        "ver": version,
        "jti": jti or str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    user_id: str, role: str, version: int = 0, jti: str | None = None
) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        role,
        TOKEN_TYPE_ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
        version=version,
        jti=jti,
    )


def create_refresh_token(
    user_id: str, role: str, version: int = 0, jti: str | None = None
) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        role,
        TOKEN_TYPE_REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
        version=version,
        jti=jti,
    )


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """校验 JWT；过期抛 TokenExpiredError，其他异常抛 UnauthorizedError。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("无效的登录凭证") from exc

    if expected_type and payload.get("type") != expected_type:
        raise UnauthorizedError("登录凭证类型不匹配")
    if payload.get("iss") != settings.jwt_issuer or payload.get(
        "aud"
    ) != settings.jwt_audience:
        # 防止跨应用重用同一密钥签发的 token（存量无 iss/aud 的 token 需重新登录）
        raise UnauthorizedError("登录凭证无效，请重新登录")
    return payload


def _fernet_key() -> bytes:
    """Fernet 密钥：由 JWT_SECRET 派生（SHA-256 → urlsafe base64，32 字节）。"""
    secret = get_settings().jwt_secret.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(digest)


def _legacy_xor_key() -> bytes:
    """旧版轻量混淆密钥（兼容迁移用，B6b 前写入的数据）。"""
    secret = get_settings().jwt_secret.encode("utf-8")
    return hashlib.sha256(secret).digest()


def _legacy_xor_decrypt(enc: str) -> str:
    try:
        data = base64.urlsafe_b64decode(enc.encode("ascii"))
    except Exception:  # noqa: BLE001
        return ""
    key = _legacy_xor_key()
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return out.decode("utf-8", errors="ignore")


def encrypt_secret(plain: str) -> str:
    """密钥加密：Fernet 对称加密（08 §8，密钥派生自 JWT_SECRET）。"""
    if not plain:
        return ""
    return Fernet(_fernet_key()).encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(enc: str) -> str:
    """密钥解密：Fernet 优先，兼容旧版 XOR 密文（B6b 前数据）。"""
    if not enc:
        return ""
    try:
        return Fernet(_fernet_key()).decrypt(enc.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # 旧版 XOR 混淆兼容
        return _legacy_xor_decrypt(enc)
    except Exception:  # noqa: BLE001
        return ""


def is_legacy_secret(enc: str) -> bool:
    """判断是否为旧版 XOR 混淆密文（Fernet 无法解密但 XOR 可解）。"""
    if not enc:
        return False
    try:
        Fernet(_fernet_key()).decrypt(enc.encode("ascii"))
        return False
    except InvalidToken:
        return bool(_legacy_xor_decrypt(enc))
    except Exception:  # noqa: BLE001
        return False


def reencrypt_secret(enc: str) -> str:
    """旧格式密文重加密为 Fernet；已是 Fernet 或空则原样返回。"""
    if is_legacy_secret(enc):
        return encrypt_secret(_legacy_xor_decrypt(enc))
    return enc
