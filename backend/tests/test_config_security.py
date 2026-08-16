"""配置安全与迁移种子静态校验（纯单元测试，无需数据库）。"""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from pydantic import ValidationError


def test_production_rejects_default_jwt_secret() -> None:
    """生产环境 + 默认 JWT_SECRET 必须启动失败（fail-closed）。"""
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="change-me-in-production")
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="")


def test_production_accepts_strong_jwt_secret() -> None:
    settings = Settings(environment="production", jwt_secret="s" * 64)
    assert settings.jwt_secret == "s" * 64


def test_development_allows_default_secret() -> None:
    """开发环境保留默认值以便本地快速启动（生产强校验不受影响）。"""
    settings = Settings(environment="development", jwt_secret="change-me-in-production")
    assert settings.environment == "development"


def test_environment_whitelist() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="staging-typo")


def test_jwt_rejects_wrong_issuer_or_audience() -> None:
    """iss/aud 不匹配的 token 必须被拒绝（防跨应用重用）。"""
    settings = get_settings()
    forged = jwt.encode(
        {
            "sub": "u-1",
            "role": "admin",
            "type": "access",
            "ver": 0,
            "jti": "x",
            "iss": "other-app",
            "aud": settings.jwt_audience,
            "iat": 0,
            "exp": 4102444800,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(UnauthorizedError):
        decode_token(forged, expected_type="access")


def test_new_migrations_must_not_seed_default_credentials() -> None:
    """0001 之后的新迁移禁止再"创建"默认凭据账号（仅做删除/清理允许）。"""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    offenders: list[str] = []
    for path in versions_dir.glob("*.py"):
        if path.name.startswith("0001_"):
            continue
        text = path.read_text(encoding="utf-8")
        # 同时出现"建账号写入"与默认口令才视为违规；0007 仅为清理旧种子
        if "INSERT INTO users" in text and "admin123" in text:
            offenders.append(path.name)
    assert offenders == [], f"新迁移中出现默认凭据：{offenders}"
