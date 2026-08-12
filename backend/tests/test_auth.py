"""登录 / RBAC 冒烟测试。"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success_and_me(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    tokens = body["data"]
    assert tokens["access_token"] and tokens["refresh_token"]

    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    me_data = me.json()["data"]
    assert me_data["username"] == "admin"
    assert me_data["role"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 40100
    assert body["data"] is None


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == 40100


@pytest.mark.asyncio
async def test_refresh_rotation(client: AsyncClient):
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    refresh_token = login.json()["data"]["refresh_token"]

    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_rbac_viewer_cannot_list_users(client: AsyncClient, create_user):
    username = f"viewer_{uuid.uuid4().hex[:8]}"
    await create_user(username, "viewer123", "只读访客", "viewer")
    login = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "viewer123"},
    )
    token = login.json()["data"]["access_token"]

    resp = await client.get(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == 40300


@pytest.mark.asyncio
async def test_admin_can_list_users(client: AsyncClient):
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = login.json()["data"]["access_token"]

    resp = await client.get(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert all(item["role"] for item in data["items"])


@pytest.mark.asyncio
async def test_validation_error_code(client: AsyncClient):
    resp = await client.post("/api/auth/login", json={"username": ""})
    assert resp.status_code == 422
    assert resp.json()["code"] == 42200


@pytest.mark.asyncio
async def test_pgvector_extension_installed(db_session):
    """验证迁移已创建 pgvector 扩展（08 §2 已确认 pgvector）。"""
    from sqlalchemy import text

    ext = await db_session.scalar(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    )
    assert ext == "vector"
