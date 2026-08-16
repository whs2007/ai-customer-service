"""客服工作台测试（13 / 开发文档 03 §5）：并发认领、回复/关闭闭环、事件作用域隔离。"""

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
    from app.core import ratelimit

    ratelimit._memory_windows.clear()
    yield
    ratelimit._memory_windows.clear()


def _solve(question: str) -> str:
    expr = question.split("=")[0].strip()
    if "+" in expr:
        a, b = expr.split("+", 1)
        return str(int(a.strip()) + int(b.strip()))
    a, b = expr.split("-", 1)
    return str(int(a.strip()) - int(b.strip()))


async def _register(client: AsyncClient, username: str) -> dict:
    cap = (await client.post("/api/auth/captcha")).json()["data"]
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "abc12345",
            "confirm_password": "abc12345",
            "captcha_id": cap["captcha_id"],
            "captcha": _solve(cap["question"]),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _make_kb(client: AsyncClient, headers, name: str) -> dict:
    resp = await client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": name, "description": "工作台测试库"},
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


async def _user_complaint(
    client: AsyncClient, admin_headers, kb_id: str
) -> tuple[dict, dict]:
    """注册用户 → 渠道配置 → 投诉转人工；返回 (user_reg, done)。"""
    await client.put(
        "/api/settings/channel",
        headers=admin_headers,
        json={"channel": "web_user", "default_kb_ids": [kb_id], "allow_human": True},
    )
    reg = await _register(client, f"u_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {reg['access_token']}"}
    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", "/api/user/chat", headers=headers, json={"message": "我要投诉！"}
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
    grouped: dict[str, list[dict]] = {}
    for event, data in events:
        grouped.setdefault(event, []).append(data)
    done = grouped["done"][0]
    assert done["ticket_no"]
    return reg, done


async def _ticket_id_by_no(ticket_no: str) -> str:
    """通过数据库定位工单 ID（测试库历史数据多，列表分页可能不含最新单）。"""
    from app.db.session import get_session_factory
    from app.models.ticket import Ticket
    from sqlalchemy import select

    async with get_session_factory()() as db:
        ticket = await db.scalar(select(Ticket).where(Ticket.ticket_no == ticket_no))
        assert ticket is not None
        return str(ticket.id)


@pytest.mark.asyncio
async def test_concurrent_claim_only_one_succeeds(
    client: AsyncClient, create_user
):
    """并发认领：两个客服同时认领同一工单，仅一个成功（13 §2.3 原子更新）。"""
    from app.db.session import get_session_factory
    from app.models.session import ChatSession
    from app.models.ticket import Ticket

    async with get_session_factory()() as db:
        session = ChatSession(user_id=None, kb_ids=[], channel="web_user")
        db.add(session)
        await db.flush()
        ticket = Ticket(
            ticket_no=f"TK{time.time_ns()}{uuid.uuid4().hex[:6]}",
            session_id=session.id,
            content="测试投诉",
            priority="high",
        )
        db.add(ticket)
        await db.commit()
        ticket_id = str(ticket.id)

    agent_headers: list[dict] = []
    for i in range(2):
        username = f"agent_{uuid.uuid4().hex[:8]}"
        await create_user(username, "test12345", f"客服{i}", "agent")
        resp = await client.post(
            "/api/auth/login", json={"username": username, "password": "test12345"}
        )
        token = resp.json()["data"]["access_token"]
        agent_headers.append({"Authorization": f"Bearer {token}"})

    results = await asyncio.gather(
        client.post(f"/api/agent/tickets/{ticket_id}/claim", headers=agent_headers[0]),
        client.post(f"/api/agent/tickets/{ticket_id}/claim", headers=agent_headers[1]),
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409]
    loser = results[0] if results[0].status_code == 409 else results[1]
    assert "已被其他客服认领" in loser.json()["message"]


@pytest.mark.asyncio
async def test_reply_close_rating_closed_loop(
    client: AsyncClient, admin_headers, create_user
):
    kb = await _make_kb(client, admin_headers, f"WB_{uuid.uuid4().hex[:8]}")
    reg, done = await _user_complaint(client, admin_headers, kb["id"])
    user_headers = {"Authorization": f"Bearer {reg['access_token']}"}
    ticket_no = done["ticket_no"]

    ticket_id = await _ticket_id_by_no(ticket_no)

    username = f"agent_{uuid.uuid4().hex[:8]}"
    await create_user(username, "test12345", "工作台客服", "agent")
    login = await client.post(
        "/api/auth/login", json={"username": username, "password": "test12345"}
    )
    agent_headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    claim = await client.post(f"/api/agent/tickets/{ticket_id}/claim", headers=agent_headers)
    assert claim.status_code == 200

    # 关闭缺少原因 → 422
    resp = await client.post(
        f"/api/agent/tickets/{ticket_id}/close", headers=agent_headers, json={"reason": ""}
    )
    assert resp.status_code == 422

    # 客服回复 → 用户端可见（role=agent）
    reply = await client.post(
        f"/api/agent/tickets/{ticket_id}/reply",
        headers=agent_headers,
        json={"content": "您好，已为您核实，正在处理中。"},
    )
    assert reply.status_code == 200
    session_detail = await client.get(
        f"/api/user/sessions/{done['session_id']}", headers=user_headers
    )
    roles = [m["role"] for m in session_detail.json()["data"]["messages"]]
    assert "agent" in roles

    # 关闭 → 用户可评价一次
    close = await client.post(
        f"/api/agent/tickets/{ticket_id}/close",
        headers=agent_headers,
        json={"reason": "已解决"},
    )
    assert close.status_code == 200
    detail = await client.get(f"/api/user/tickets/{ticket_id}", headers=user_headers)
    d = detail.json()["data"]
    assert d["ticket"]["status"] == "closed"
    assert d["can_rate"] is True
    rate = await client.post(
        f"/api/user/tickets/{ticket_id}/rating",
        headers=user_headers,
        json={"score": 5, "comment": "很满意"},
    )
    assert rate.status_code == 200
    rate2 = await client.post(
        f"/api/user/tickets/{ticket_id}/rating",
        headers=user_headers,
        json={"score": 1},
    )
    assert rate2.status_code == 409

    # 方案 A：工单写操作审计留痕
    audit = (
        await client.get("/api/audit-logs?page_size=50", headers=admin_headers)
    ).json()["data"]["items"]
    actions = {a["action"] for a in audit}
    assert {"ticket_claim", "ticket_reply", "ticket_close"} <= actions

    # 管理端看板与工单状态一致
    overview = await client.get("/api/admin/tickets/overview", headers=admin_headers)
    data = overview.json()["data"]
    assert data["total"] >= 1
    assert data["closed_today"] >= 1


@pytest.mark.asyncio
async def test_event_scope_isolation(client: AsyncClient, admin_headers, create_user):
    """事件作用域隔离（13 §4 / 开发文档 01 §7.3）：服务端过滤，严禁跨用户泄漏。

    注：httpx 0.27 ASGITransport 对无限流会整体缓冲，无法在测试端增量读取 SSE；
    因此这里直接对 EventBus 订阅/发布做服务级验证（安全过滤核心逻辑），
    HTTP 端点另做可达性与 scope-role 强制校验（见 test_event_http_permissions）。
    """
    import asyncio as _asyncio

    from app.services.event_service import Subscriber, bus, publish_event

    async def collect(scope: str, user_id: str) -> tuple[asyncio.Queue, list[dict]]:
        queue: asyncio.Queue = asyncio.Queue()
        bus.subscribe(Subscriber(scope=scope, user_id=user_id, queue=queue))
        return queue, []

    q_a, _ = await collect("user", "user-a")
    q_b, _ = await collect("user", "user-b")
    q_agent, _ = await collect("agent", "agent-1")
    q_admin, _ = await collect("admin", "admin-1")
    try:
        def _drain(q: asyncio.Queue) -> list[dict]:
            items = []
            while not q.empty():
                items.append(q.get_nowait())
            return items

        base = {
            "session_id": str(uuid.uuid4()),
            "ticket_status": "open",
            "assignee_id": None,
        }
        # ticket.created：归属用户 A + 待处理（全员客服）+ 管理员；用户 B 不可见
        publish_event(
            "ticket.created",
            {**base, "ticket_id": str(uuid.uuid4()), "ticket_no": "TK1", "user_id": "user-a", "priority": "high"},
        )
        await _asyncio.sleep(0.05)
        got_a = _drain(q_a)
        got_b = _drain(q_b)
        got_agent = _drain(q_agent)
        got_admin = _drain(q_admin)
        assert [e["event"] for e in got_a] == ["ticket.created"]
        assert got_b == []
        assert [e["event"] for e in got_agent] == ["ticket.created"]
        assert [e["event"] for e in got_admin] == ["ticket.created"]
        assert all(e.get("event_id") for e in got_a + got_agent + got_admin)

        # ticket.claimed：仍归属用户 A；已认领后仅 assignee 客服可见
        publish_event(
            "ticket.claimed",
            {
                **base,
                "ticket_status": "processing",
                "assignee_id": "agent-1",
                "ticket_id": str(uuid.uuid4()),
                "ticket_no": "TK2",
                "user_id": "user-a",
                "claimed_at": "2026-08-16T00:00:00Z",
            },
        )
        await _asyncio.sleep(0.05)
        assert [e["event"] for e in _drain(q_a)] == ["ticket.claimed"]
        assert _drain(q_b) == []
        assert [e["event"] for e in _drain(q_agent)] == ["ticket.claimed"]
        _drain(q_admin)

        # message.new（人工回复）：用户 A + 该 assignee 客服；用户 B 不可见
        publish_event(
            "message.new",
            {
                **base,
                "ticket_status": "processing",
                "assignee_id": "agent-1",
                "message_id": str(uuid.uuid4()),
                "role": "agent",
                "user_id": "user-a",
                "from_agent": "agent-1",
            },
        )
        await _asyncio.sleep(0.05)
        assert [e["event"] for e in _drain(q_a)] == ["message.new"]
        assert _drain(q_b) == []
        assert [e["event"] for e in _drain(q_agent)] == ["message.new"]
        assert [e["event"] for e in _drain(q_admin)] == ["message.new"]

        # 另一客服（agent-2）不是 assignee，收不到已认领会话的消息
        q_other, _ = await collect("agent", "agent-2")
        try:
            publish_event(
                "message.new",
                {
                    **base,
                    "ticket_status": "processing",
                    "assignee_id": "agent-1",
                    "message_id": str(uuid.uuid4()),
                    "role": "agent",
                    "user_id": "user-a",
                    "from_agent": "agent-1",
                },
            )
            await _asyncio.sleep(0.05)
            assert _drain(q_other) == []
        finally:
            bus.unsubscribe(q_other)
    finally:
        bus.unsubscribe(q_a)
        bus.unsubscribe(q_b)
        bus.unsubscribe(q_agent)
        bus.unsubscribe(q_admin)


@pytest.mark.asyncio
async def test_event_http_permissions(client: AsyncClient, create_user):
    """SSE 端点可达性 + scope 与角色强制匹配（13 §4）。"""
    username = f"u_{uuid.uuid4().hex[:8]}"
    await create_user(username, "test12345", "事件用户", "user")
    login = await client.post(
        "/api/auth/login", json={"username": username, "password": "test12345"}
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    # user 角色订阅 scope=agent → 403
    resp = await client.get("/api/stream/events?scope=agent", headers=headers)
    assert resp.status_code == 403
    # 非法 scope → 422
    resp = await client.get("/api/stream/events?scope=other", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_event_sse_connection_limit(client: AsyncClient, create_user, monkeypatch):
    """P1-4：SSE 连接数达到上限时返回 429，防止单实例连接失控。"""
    class _FakeSettings:
        sse_max_connections = 0

    monkeypatch.setattr(
        "app.api.routes.events.get_settings", lambda: _FakeSettings()
    )
    username = f"sse_{uuid.uuid4().hex[:8]}"
    await create_user(username, "test12345", "事件用户", "user")
    login = await client.post(
        "/api/auth/login", json={"username": username, "password": "test12345"}
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    resp = await client.get("/api/stream/events?scope=user", headers=headers)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_concurrent_read_cursor_no_conflict():
    """审计 M4：并发已读游标 upsert 原子化，不得触发唯一约束 500。"""
    import uuid as _uuid

    from app.db.session import get_session_factory
    from app.models.message import Message
    from app.models.session import ChatSession
    from app.models.user import User
    from app.services import read_service
    from sqlalchemy import select

    async with get_session_factory()() as db:
        user = User(
            username=f"rc_{_uuid.uuid4().hex[:8]}",
            password_hash="x",
            display_name="游标测试",
            role="user",
        )
        db.add(user)
        await db.flush()
        session = ChatSession(user_id=user.id, kb_ids=[], channel="web_user")
        db.add(session)
        await db.flush()
        msg = Message(session_id=session.id, role="user", content="hi")
        db.add(msg)
        await db.commit()
        session_id = session.id
        user_id = user.id

    async def _do() -> None:
        async with get_session_factory()() as db:
            await read_service.upsert_read_cursor(
                db, session_id, "user", user_id, None
            )

    await asyncio.gather(_do(), _do())

    async with get_session_factory()() as db:
        from app.models.session_read import SessionRead
        from sqlalchemy import delete

        cursor = await db.scalar(
            select(SessionRead).where(
                SessionRead.session_id == session_id,
                SessionRead.reader_role == "user",
                SessionRead.reader_id == user_id,
            )
        )
        assert cursor is not None
        await db.delete(cursor)
        await db.execute(delete(Message).where(Message.session_id == session_id))
        await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.mark.asyncio
async def test_agent_read_requires_ownership(
    client: AsyncClient, create_user, admin_headers
):
    """审计 M5：agent 只能对 open 或自己负责的工单会话写已读游标。"""

    from app.db.session import get_session_factory
    from app.models.session import ChatSession
    from app.models.ticket import Ticket

    async with get_session_factory()() as db:
        session = ChatSession(user_id=None, kb_ids=[], channel="web_user")
        db.add(session)
        await db.flush()
        ticket = Ticket(
            ticket_no=f"TK{time.time_ns()}{uuid.uuid4().hex[:6]}",
            session_id=session.id,
            content="测试",
            priority="medium",
        )
        db.add(ticket)
        await db.commit()
        session_id = str(session.id)
        ticket_id = str(ticket.id)

    agents = []
    for tag in ("a", "b"):
        username = f"rb_{tag}_{uuid.uuid4().hex[:8]}"
        await create_user(username, "test12345", f"客服{tag}", "agent")
        resp = await client.post(
            "/api/auth/login", json={"username": username, "password": "test12345"}
        )
        agents.append({"Authorization": f"Bearer {resp.json()['data']['access_token']}"})

    # agent A 认领 → processing；agent B 对该会话写已读 → 403
    claim = await client.post(f"/api/agent/tickets/{ticket_id}/claim", headers=agents[0])
    assert claim.status_code == 200
    r = await client.post(
        f"/api/agent/sessions/{session_id}/read",
        headers=agents[1],
        json={"last_read_message_id": None},
    )
    assert r.status_code == 403
    # 列表权限对齐：agent B 的"处理中"队列不应出现 agent A 负责的单（11 §10.1）
    list_b = await client.get(
        "/api/agent/tickets?status=processing&page_size=100", headers=agents[1]
    )
    assert all(t["id"] != ticket_id for t in list_b.json()["data"]["items"])
    # admin 可见全部
    admin_list = await client.get(
        "/api/agent/tickets?status=processing&page_size=100", headers=admin_headers
    )
    assert any(t["id"] == ticket_id for t in admin_list.json()["data"]["items"])
    # agent A（assignee）可写
    r = await client.post(
        f"/api/agent/sessions/{session_id}/read",
        headers=agents[0],
        json={"last_read_message_id": None},
    )
    assert r.status_code == 200

    async with get_session_factory()() as db:
        from sqlalchemy import delete

        await db.execute(delete(Ticket).where(Ticket.id == ticket_id))
        await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
        await db.commit()


@pytest.mark.asyncio
async def test_release_ticket_back_to_open(
    client: AsyncClient, create_user, admin_headers
):
    """释放工单（新增能力）：assignee 释放 → 回到 open、清空负责人，其他客服可重新认领。"""
    from app.db.session import get_session_factory
    from app.models.session import ChatSession
    from app.models.ticket import Ticket
    from app.models.ticket_note import TicketNote
    from sqlalchemy import select

    async with get_session_factory()() as db:
        session = ChatSession(user_id=None, kb_ids=[], channel="web_user")
        db.add(session)
        await db.flush()
        ticket = Ticket(
            ticket_no=f"TK{time.time_ns()}{uuid.uuid4().hex[:6]}",
            session_id=session.id,
            content="释放测试",
            priority="medium",
        )
        db.add(ticket)
        await db.commit()
        ticket_id = str(ticket.id)
        session_id = str(session.id)

    agents = []
    for tag in ("a", "b"):
        username = f"rl_{tag}_{uuid.uuid4().hex[:8]}"
        await create_user(username, "test12345", f"客服{tag}", "agent")
        resp = await client.post(
            "/api/auth/login", json={"username": username, "password": "test12345"}
        )
        agents.append({"Authorization": f"Bearer {resp.json()['data']['access_token']}"})

    # A 认领 → processing
    claim = await client.post(f"/api/agent/tickets/{ticket_id}/claim", headers=agents[0])
    assert claim.status_code == 200

    # 非负责人（B）释放 → 403
    r = await client.post(
        f"/api/agent/tickets/{ticket_id}/release",
        headers=agents[1],
        json={"reason": "越权释放"},
    )
    assert r.status_code == 403

    # 负责人（A）释放 → open，清空 assignee/claimed_at
    r = await client.post(
        f"/api/agent/tickets/{ticket_id}/release",
        headers=agents[0],
        json={"reason": "用户要求重新排队"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "open"
    # 方案 A：释放操作审计留痕
    audit = (
        await client.get("/api/audit-logs?page_size=50", headers=admin_headers)
    ).json()["data"]["items"]
    assert any(a["action"] == "ticket_release" for a in audit)

    async with get_session_factory()() as db:
        row = await db.get(Ticket, uuid.UUID(ticket_id))
        assert row.status == "open"
        assert row.assignee_id is None
        assert row.claimed_at is None
        notes = (
            await db.execute(
                select(TicketNote).where(TicketNote.ticket_id == ticket_id)
            )
        ).scalars().all()
        assert any(n.note.startswith("释放工单") for n in notes)

    # 释放后 B 可重新认领
    re_claim = await client.post(
        f"/api/agent/tickets/{ticket_id}/claim", headers=agents[1]
    )
    assert re_claim.status_code == 200

    # 已释放后 admin 也可释放（任何 processing 单）
    # 职责分离：admin 默认只读，释放 → 403
    r = await client.post(
        f"/api/agent/tickets/{ticket_id}/release",
        headers=admin_headers,
        json={"reason": "管理员释放"},
    )
    assert r.status_code == 403

    # 清理
    async with get_session_factory()() as db:
        from sqlalchemy import delete

        await db.execute(delete(TicketNote).where(TicketNote.ticket_id == ticket_id))
        await db.execute(delete(Ticket).where(Ticket.id == ticket_id))
        await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
        await db.commit()


@pytest.mark.asyncio
async def test_admin_ticket_ops_gated_by_setting(
    client: AsyncClient, create_user, admin_headers, monkeypatch
):
    """职责分离：admin 默认不能认领（403）；开启 allow_admin_ticket_ops 后可操作。"""
    from app.db.session import get_session_factory
    from app.models.session import ChatSession
    from app.models.ticket import Ticket
    from app.models.ticket_note import TicketNote

    async with get_session_factory()() as db:
        session = ChatSession(user_id=None, kb_ids=[], channel="web_user")
        db.add(session)
        await db.flush()
        ticket = Ticket(
            ticket_no=f"TK{time.time_ns()}{uuid.uuid4().hex[:6]}",
            session_id=session.id,
            content="权限测试",
            priority="medium",
        )
        db.add(ticket)
        await db.commit()
        ticket_id = str(ticket.id)
        session_id = str(session.id)

    # 默认：admin 认领 → 403
    r = await client.post(f"/api/agent/tickets/{ticket_id}/claim", headers=admin_headers)
    assert r.status_code == 403

    # 开启开关后：admin 可认领
    class _FakeSettings:
        allow_admin_ticket_ops = True

    monkeypatch.setattr(
        "app.api.deps.get_settings", lambda: _FakeSettings()
    )
    monkeypatch.setattr(
        "app.services.ticket_service.get_settings", lambda: _FakeSettings()
    )
    r = await client.post(f"/api/agent/tickets/{ticket_id}/claim", headers=admin_headers)
    assert r.status_code == 200

    # 清理
    async with get_session_factory()() as db:
        from sqlalchemy import delete

        await db.execute(delete(TicketNote).where(TicketNote.ticket_id == ticket_id))
        await db.execute(delete(Ticket).where(Ticket.id == ticket_id))
        await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
        await db.commit()
