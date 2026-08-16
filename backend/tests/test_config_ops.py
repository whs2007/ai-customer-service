"""配置接线测试：/metrics 开关与抓取 token、敏感词 API、上传限制、日志清理任务。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import Settings
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_disabled_returns_404(
    client: AsyncClient, admin_headers, monkeypatch
):
    """metrics_enabled=false 时 /metrics 必须 404（开关接线）。"""
    monkeypatch.setattr(
        "app.api.routes.health.get_settings",
        lambda: Settings(environment="test", jwt_secret="s" * 32, metrics_enabled=False),
    )
    resp = await client.get("/metrics", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_metrics_accepts_static_token(
    client: AsyncClient, admin_headers, monkeypatch
):
    """配置 METRICS_TOKEN 后，Prometheus 可用静态 token 抓取（无需 admin JWT）。"""
    monkeypatch.setattr(
        "app.api.routes.health.get_settings",
        lambda: Settings(
            environment="test",
            jwt_secret="s" * 32,
            metrics_enabled=True,
            metrics_token="prom-token-123",
        ),
    )
    resp = await client.get(
        "/metrics", headers={"Authorization": "Bearer prom-token-123"}
    )
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text

    wrong = await client.get(
        "/metrics", headers={"Authorization": "Bearer wrong-token"}
    )
    assert wrong.status_code in (401, 403)


@pytest.mark.asyncio
async def test_moderation_words_api(client: AsyncClient, admin_headers, db_session):
    """敏感词管理 API：管理员可在线覆盖本地兜底词表。"""
    from app.core.moderation import DEFAULT_SENSITIVE_WORDS, get_sensitive_words

    words = ["测试敏感词A", "测试敏感词B"]
    resp = await client.put(
        "/api/settings/moderation/words",
        headers=admin_headers,
        json={"words": words},
    )
    assert resp.status_code == 200

    got = (await client.get("/api/settings/moderation/words", headers=admin_headers)).json()
    assert got["data"]["words"] == words
    assert await get_sensitive_words(db_session) == words

    # 非 admin 禁止
    forbidden = await client.get("/api/settings/moderation/words")
    assert forbidden.status_code in (401, 403)

    # 恢复默认，避免影响其他用例
    await client.put(
        "/api/settings/moderation/words",
        headers=admin_headers,
        json={"words": DEFAULT_SENSITIVE_WORDS},
    )


@pytest.mark.asyncio
async def test_upload_size_limit_configurable(
    client: AsyncClient, admin_headers, monkeypatch
):
    """上传大小上限可配置：max_upload_size_mb=1 时大于 1MB 的文件被拒绝。"""
    monkeypatch.setattr(
        "app.pipeline.parser.get_settings",
        lambda: Settings(environment="test", jwt_secret="s" * 32, max_upload_size_mb=1),
    )
    kb = (
        await client.post(
            "/api/knowledge-bases",
            headers=admin_headers,
            json={"name": f"UPS_{uuid.uuid4().hex[:8]}", "description": ""},
        )
    ).json()["data"]
    big = await client.post(
        f"/api/knowledge-bases/{kb['id']}/documents",
        headers=admin_headers,
        files={"file": ("big.txt", b"x" * (1024 * 1024 + 10), "text/plain")},
    )
    assert big.status_code == 400
    assert "大小" in big.json()["message"]


@pytest.mark.asyncio
async def test_maintenance_prunes_old_trace_logs(db_session):
    """日志清理任务：仅删除超过 log_retention_days 的 trace_logs。"""
    from app.models.session import ChatSession
    from app.models.trace_log import TraceLog
    from app.workers.tasks import prune_expired_trace_logs

    chat_session = ChatSession(kb_ids=[])
    db_session.add(chat_session)
    await db_session.flush()

    old = TraceLog(
        session_id=chat_session.id,
        request_id=uuid.uuid4().hex[:32],
        steps=[],
        latency_ms=1,
        created_at=datetime.now(UTC) - timedelta(days=60),
    )
    fresh = TraceLog(
        session_id=chat_session.id,
        request_id=uuid.uuid4().hex[:32],
        steps=[],
        latency_ms=1,
        created_at=datetime.now(UTC),
    )
    db_session.add_all([old, fresh])
    await db_session.commit()
    old_id, fresh_id = old.id, fresh.id

    removed = await prune_expired_trace_logs()
    assert removed >= 1

    from sqlalchemy import select

    still_exists = await db_session.scalar(
        select(TraceLog.id).where(TraceLog.id.in_([old_id, fresh_id]))
    )
    assert still_exists == fresh_id
