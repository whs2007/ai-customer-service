"""会话令牌安全测试：版本声明、轮换复用检测、改密失效（DB 用例在无 PG 时自动跳过）。"""

from __future__ import annotations

import uuid

import pytest
from app.core.security import create_access_token, create_refresh_token, decode_token


def test_token_carries_version_and_jti() -> None:
    """JWT 载荷携带会话版本号与 jti（服务端吊销的基础）。"""
    access = decode_token(
        create_access_token("u-1", "admin", version=3), expected_type="access"
    )
    assert access["ver"] == 3
    assert access["jti"]

    refresh = decode_token(
        create_refresh_token("u-1", "agent", version=5, jti="jti-abc"),
        expected_type="refresh",
    )
    assert refresh["ver"] == 5
    assert refresh["jti"] == "jti-abc"


@pytest.mark.asyncio
async def test_refresh_reuse_rejected(client, admin_headers):
    """轮换后旧 refresh token 再次使用必须被拒绝（复用检测）。"""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    old_refresh = login.json()["data"]["refresh_token"]

    first = await client.post(
        "/api/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert first.status_code == 200

    reuse = await client.post(
        "/api/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert reuse.status_code == 401
    assert reuse.json()["code"] == 40100


@pytest.mark.asyncio
async def test_password_reset_invalidates_all_tokens(client, admin_headers):
    """重置密码后旧 access/refresh 全部失效。"""
    username = f"reset_{uuid.uuid4().hex[:8]}"
    created = (
        await client.post(
            "/api/auth/users",
            headers=admin_headers,
            json={
                "username": username,
                "password": "pass123456",
                "display_name": "待重置",
                "role": "agent",
            },
        )
    ).json()["data"]

    login = await client.post(
        "/api/auth/login", json={"username": username, "password": "pass123456"}
    )
    tokens = login.json()["data"]

    reset = await client.put(
        f"/api/auth/users/{created['id']}/password",
        headers=admin_headers,
        json={"password": "newpass888"},
    )
    assert reset.status_code == 200

    old_me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert old_me.status_code == 401

    old_refresh = await client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert old_refresh.status_code == 401

    # 新密码可正常登录
    new_login = await client.post(
        "/api/auth/login", json={"username": username, "password": "newpass888"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_role_change_invalidates_old_token(client, admin_headers):
    """角色变更后旧 token（含旧角色声明）立即失效。"""
    username = f"role_{uuid.uuid4().hex[:8]}"
    created = (
        await client.post(
            "/api/auth/users",
            headers=admin_headers,
            json={
                "username": username,
                "password": "pass123456",
                "display_name": "改角色",
                "role": "viewer",
            },
        )
    ).json()["data"]
    login = await client.post(
        "/api/auth/login", json={"username": username, "password": "pass123456"}
    )
    old_token = login.json()["data"]["access_token"]

    await client.put(
        f"/api/auth/users/{created['id']}",
        headers=admin_headers,
        json={"role": "agent"},
    )

    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert me.status_code == 401
