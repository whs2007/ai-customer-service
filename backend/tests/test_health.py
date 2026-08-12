"""/health 冒烟测试。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] == "ok"
    assert body["data"]["components"]["database"] == "ok"
    assert body["data"]["components"]["redis"] == "skipped"


@pytest.mark.asyncio
async def test_health_has_version(client: AsyncClient):
    resp = await client.get("/health")
    data = resp.json()["data"]
    assert data["app"] == "AI 智能客服系统"
    assert data["version"]

