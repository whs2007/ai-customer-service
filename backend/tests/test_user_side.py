"""用户端测试（12 / 开发文档 03 §5）：注册、登录锁定、越权、脱敏、渠道配置、工单。"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

SAMPLE_XLSX = (
    Path(__file__).resolve().parents[1] / "samples" / "FAQ知识库导入模板.xlsx"
)


@pytest.fixture(autouse=True)
def _clear_ratelimit_windows():
    """清理进程内限流窗口，避免测试间相互影响。"""
    from app.core import ratelimit

    ratelimit._memory_windows.clear()
    yield
    ratelimit._memory_windows.clear()


def _solve(question: str) -> str:
    """解析算术验证码题目（如 '3 + 5 = ?'）。"""
    expr = question.split("=")[0].strip()
    if "+" in expr:
        a, b = expr.split("+", 1)
        return str(int(a.strip()) + int(b.strip()))
    a, b = expr.split("-", 1)
    return str(int(a.strip()) - int(b.strip()))


async def _register(
    client: AsyncClient,
    username: str,
    password: str = "abc12345",
    display_name: str | None = None,
    captcha: str | None = None,
):
    cap = await client.post("/api/auth/captcha")
    assert cap.status_code == 200
    data = cap.json()["data"]
    payload = {
        "username": username,
        "password": password,
        "confirm_password": password,
        "display_name": display_name,
        "captcha_id": data["captcha_id"],
        "captcha": captcha if captcha is not None else _solve(data["question"]),
    }
    return await client.post("/api/auth/register", json=payload)


async def _make_kb(client: AsyncClient, headers, name: str) -> dict:
    resp = await client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": name, "description": "用户端测试库"},
    )
    kb = resp.json()["data"]
    with SAMPLE_XLSX.open("rb") as f:
        upload = await client.post(
            f"/api/knowledge-bases/{kb['id']}/documents",
            headers=headers,
            files={"file": ("FAQ知识库导入模板.xlsx", f, "application/octet-stream")},
        )
    doc_id = upload.json()["data"]["document_id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        doc = (
            await client.get(f"/api/documents/{doc_id}", headers=headers)
        ).json()["data"]
        if doc["status"] in ("completed", "failed"):
            assert doc["status"] == "completed"
            return kb
        await asyncio.sleep(0.2)
    raise TimeoutError(f"文档处理超时: {doc_id}")


async def _setup_channel(client: AsyncClient, admin_headers, kb_id: str) -> None:
    resp = await client.put(
        "/api/settings/channel",
        headers=admin_headers,
        json={
            "channel": "web_user",
            "default_kb_ids": [kb_id],
            "allow_human": True,
            "business_hours": None,
        },
    )
    assert resp.status_code == 200, resp.text


async def _user_chat_events(
    client: AsyncClient, headers, payload
) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", "/api/user/chat", headers=headers, json=payload
    ) as resp:
        current = None
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((current, json.loads(line.split(":", 1)[1].strip())))
    return events


def _grouped(events: list[tuple[str, dict]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for event, data in events:
        out.setdefault(event, []).append(data)
    return out


@pytest.mark.asyncio
async def test_register_auto_login_and_me(client: AsyncClient):
    username = f"user_{uuid.uuid4().hex[:8]}"
    resp = await _register(client, username, display_name="测试用户")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["user"]["role"] == "user"
    assert data["user"]["status"] == "active"
    assert data["access_token"] and data["refresh_token"]
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["data"]["username"] == username


@pytest.mark.asyncio
async def test_register_validation_failures(client: AsyncClient):
    username = f"user_{uuid.uuid4().hex[:8]}"
    # 弱密码
    resp = await _register(client, username, password="12345678")
    assert resp.status_code == 400
    # 两次密码不一致
    cap = (await client.post("/api/auth/captcha")).json()["data"]
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": f"{username}b",
            "password": "abc12345",
            "confirm_password": "abc12346",
            "captcha_id": cap["captcha_id"],
            "captcha": _solve(cap["question"]),
        },
    )
    assert resp.status_code == 400
    # 验证码错误
    resp = await _register(client, f"{username}c", captcha="999")
    assert resp.status_code == 400
    # 用户名已存在
    resp = await _register(client, username)
    assert resp.status_code == 200
    resp = await _register(client, username)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_rate_limit(client: AsyncClient):
    """同 IP 高频注册被限流（12 §2.1：每分钟 ≤ 5 次）。"""
    responses = []
    for _ in range(6):
        cap = (await client.post("/api/auth/captcha")).json()["data"]
        resp = await client.post(
            "/api/auth/register",
            json={
                "username": f"rl_{uuid.uuid4().hex[:8]}",
                "password": "abc12345",
                "confirm_password": "abc12345",
                "captcha_id": cap["captcha_id"],
                "captcha": _solve(cap["question"]),
            },
        )
        responses.append(resp.status_code)
    assert responses[:5] == [200] * 5
    assert responses[5] == 429


@pytest.mark.asyncio
async def test_login_lockout_after_failures(client: AsyncClient, create_user):
    username = f"lock_{uuid.uuid4().hex[:8]}"
    await create_user(username, "test12345", "锁定测试", "user")
    for _ in range(5):
        resp = await client.post(
            "/api/auth/login", json={"username": username, "password": "wrong-pass"}
        )
        assert resp.status_code == 401
    # 第 6 次即使密码正确也被锁定（15 分钟）
    resp = await client.post(
        "/api/auth/login", json={"username": username, "password": "test12345"}
    )
    assert resp.status_code == 401
    assert "锁定" in resp.json()["message"]


@pytest.mark.asyncio
async def test_user_chat_sanitized_and_channel_kb(
    client: AsyncClient, admin_headers
):
    kb = await _make_kb(client, admin_headers, f"USR_{uuid.uuid4().hex[:8]}")
    await _setup_channel(client, admin_headers, kb["id"])
    username = f"user_{uuid.uuid4().hex[:8]}"
    reg = (await _register(client, username)).json()["data"]
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    events = await _user_chat_events(
        client, headers, {"session_id": None, "message": "商品签收后几天可以退货？"}
    )
    grouped = _grouped(events)
    assert "message_start" in grouped and "done" in grouped
    done = grouped["done"][0]
    assert done["intent"] == "policy_query"
    citations = grouped["citations"][0]["citations"]
    assert citations
    # 用户端引用脱敏：只含 document_name/question（11 §10）
    assert set(citations[0].keys()) == {"document_name", "question"}
    assert "chunk_id" not in citations[0]
    assert "kb_id" not in citations[0]

    session_id = done["session_id"]
    detail = await client.get(f"/api/user/sessions/{session_id}", headers=headers)
    assert detail.status_code == 200
    d = detail.json()["data"]
    assert d["session"]["id"] == session_id
    msg_keys = set(d["messages"][0].keys())
    # 不含内部字段
    assert not (msg_keys & {"intent", "cited_chunk_ids", "trace", "citations"})


@pytest.mark.asyncio
async def test_user_cross_access_forbidden(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"USR2_{uuid.uuid4().hex[:8]}")
    await _setup_channel(client, admin_headers, kb["id"])
    user_a = (await _register(client, f"ua_{uuid.uuid4().hex[:8]}")).json()["data"]
    user_b = (await _register(client, f"ub_{uuid.uuid4().hex[:8]}")).json()["data"]
    headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

    events = await _user_chat_events(
        client, headers_a, {"session_id": None, "message": "退款多久到账？"}
    )
    session_id = _grouped(events)["done"][0]["session_id"]

    # 用户 B 读取用户 A 的会话 → 403
    resp = await client.get(f"/api/user/sessions/{session_id}", headers=headers_b)
    assert resp.status_code == 403
    # 用户 B 用 A 的会话 ID 发消息 → SSE error 40300
    events_b = await _user_chat_events(
        client, headers_b, {"session_id": session_id, "message": "你好"}
    )
    grouped_b = _grouped(events_b)
    assert grouped_b["error"][0]["code"] == "40300"

    # 用户 B 的会话列表不含 A 的会话
    lst = (await client.get("/api/user/sessions", headers=headers_b)).json()["data"]
    assert all(s["id"] != session_id for s in lst["items"])


@pytest.mark.asyncio
async def test_change_password_invalidates_tokens(client: AsyncClient):
    username = f"pwd_{uuid.uuid4().hex[:8]}"
    reg = (await _register(client, username)).json()["data"]
    headers = {"Authorization": f"Bearer {reg['access_token']}"}
    resp = await client.put(
        "/api/auth/password",
        headers=headers,
        json={"old_password": "abc12345", "new_password": "xyz67890"},
    )
    assert resp.status_code == 200
    # 旧 access token 已失效（token_version+1）
    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 401
    # 新密码可登录
    login = await client.post(
        "/api/auth/login", json={"username": username, "password": "xyz67890"}
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_transferred_message_publishes_message_new(
    client: AsyncClient, admin_headers
):
    """审计 H2：转人工后用户继续留言，需发布 message.new 供客服端实时可见（12 §3.3）。"""
    kb = await _make_kb(client, admin_headers, f"H2_{uuid.uuid4().hex[:8]}")
    await _setup_channel(client, admin_headers, kb["id"])
    reg = (await _register(client, f"h2_{uuid.uuid4().hex[:8]}")).json()["data"]
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    events = await _user_chat_events(client, headers, {"message": "我要投诉！"})
    session_id = _grouped(events)["done"][0]["session_id"]

    from app.services.event_service import Subscriber, bus

    queue: asyncio.Queue = asyncio.Queue()
    bus.subscribe(Subscriber(scope="user", user_id=str(reg["user"]["id"]), queue=queue))
    try:
        events2 = await _user_chat_events(
            client, headers, {"session_id": session_id, "message": "转人工后再问一句"}
        )
        assert _grouped(events2)["done"][0]["intent"] == "transfer"
        await asyncio.sleep(0.1)
        got = []
        while not queue.empty():
            got.append(queue.get_nowait())
        hits = [
            e
            for e in got
            if e["event"] == "message.new"
            and e.get("role") == "user"
            and e.get("session_id") == session_id
        ]
        assert hits, f"未收到 message.new 事件: {got}"
        assert hits[0]["message_id"]
    finally:
        bus.unsubscribe(queue)


@pytest.mark.asyncio
async def test_concurrent_register_same_username_no_500(monkeypatch, create_user):
    """审计 M3：并发同名注册，一个成功一个 409，不得出现 500。"""
    from app.schemas.auth import RegisterRequest
    from app.services import auth_service

    def _fake_verify(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_service, "verify_captcha", _fake_verify)
    username = f"dup_{uuid.uuid4().hex[:8]}"
    payload = RegisterRequest(
        username=username,
        password="abc12345",
        confirm_password="abc12345",
        captcha_id="x",
        captcha="1",
    )

    from app.core.exceptions import ConflictError
    from app.db.session import get_session_factory

    async def _do() -> str:
        async with get_session_factory()() as db:
            try:
                await auth_service.register_user(db, payload, ip="127.0.0.1")
                return "ok"
            except ConflictError:
                return "conflict"

    results = await asyncio.gather(_do(), _do())
    assert sorted(results) == ["conflict", "ok"], results
