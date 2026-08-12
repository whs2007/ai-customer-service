"""B4 智能应答测试：四类路由、SSE 事件、表单收集、转人工落库、引用反馈、会话恢复、RBAC。"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

SAMPLE_XLSX = (
    Path(__file__).resolve().parents[1] / "samples" / "FAQ知识库导入模板.xlsx"
)


async def _wait_document(client: AsyncClient, headers, doc_id, timeout=15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/documents/{doc_id}", headers=headers)
        doc = resp.json()["data"]
        if doc["status"] in ("completed", "failed"):
            return doc
        await asyncio.sleep(0.2)
    raise TimeoutError(f"文档处理超时: {doc_id}")


async def _make_kb(client: AsyncClient, headers, name: str) -> dict:
    resp = await client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": name, "description": "B4 对话测试库"},
    )
    kb = resp.json()["data"]
    with SAMPLE_XLSX.open("rb") as f:
        upload = await client.post(
            f"/api/knowledge-bases/{kb['id']}/documents",
            headers=headers,
            files={"file": ("FAQ知识库导入模板.xlsx", f, "application/octet-stream")},
        )
    doc = await _wait_document(client, headers, upload.json()["data"]["document_id"])
    assert doc["status"] == "completed"
    return kb


async def chat_events(client: AsyncClient, headers, payload) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream("POST", "/api/chat", headers=headers, json=payload) as resp:
        assert resp.status_code == 200, resp.text
        current_event = None
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((current_event, json.loads(line.split(":", 1)[1].strip())))
    return events


def events_dict(events: list[tuple[str, dict]]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for event, data in events:
        grouped.setdefault(event, []).append(data)
    return grouped


@pytest.mark.asyncio
async def test_order_query_with_order_no(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4O_{uuid.uuid4().hex[:8]}")
    events = await chat_events(
        client,
        admin_headers,
        {
            "kb_ids": [kb["id"]],
            "message": "查一下订单号 202608120001234 的物流",
        },
    )
    grouped = events_dict(events)
    assert "message_start" in grouped and "done" in grouped
    done = grouped["done"][0]
    assert done["intent"] == "order_query"
    assert done["ticket_no"] is None
    tokens = "".join(d["content"] for d in grouped.get("token", []))
    assert "202608120001234" in tokens
    assert "顺丰速运" in tokens
    session_id = done["session_id"]

    detail = await client.get(f"/api/sessions/{session_id}", headers=admin_headers)
    assert detail.status_code == 200
    roles = [m["role"] for m in detail.json()["data"]["messages"]]
    assert roles == ["user", "assistant"]


@pytest.mark.asyncio
async def test_order_without_order_no_collects_form(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4F_{uuid.uuid4().hex[:8]}")
    events = await chat_events(
        client, admin_headers, {"kb_ids": [kb["id"]], "message": "查询我的订单"}
    )
    grouped = events_dict(events)
    assert "form" in grouped
    fields = grouped["form"][0]["fields"]
    assert any(f["name"] == "order_no" and f["pattern"] == r"^\d{15}$" for f in fields)
    session_id = grouped["done"][0]["session_id"]

    # 提交表单：订单号作为上下文注入 → 工具查询
    events2 = await chat_events(
        client,
        admin_headers,
        {
            "session_id": session_id,
            "kb_ids": [kb["id"]],
            "message": "已填写",
            "form_data": {"order_no": "123456789012345", "contact": "13800138000"},
        },
    )
    grouped2 = events_dict(events2)
    assert grouped2["done"][0]["intent"] == "order_query"
    tokens2 = "".join(d["content"] for d in grouped2.get("token", []))
    assert "123456789012345" in tokens2
    assert "已为您查询订单" in tokens2


@pytest.mark.asyncio
async def test_policy_query_with_citations(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4P_{uuid.uuid4().hex[:8]}")
    events = await chat_events(
        client,
        admin_headers,
        {"kb_ids": [kb["id"]], "message": "商品签收后几天可以退货？"},
    )
    grouped = events_dict(events)
    assert grouped["done"][0]["intent"] == "policy_query"
    citations = grouped["citations"][0]["citations"]
    assert citations
    first = citations[0]
    assert first["kb_id"] == kb["id"]
    assert first["document_name"].endswith(".xlsx")
    assert "retrieval_score" in first
    tokens = "".join(d["content"] for d in grouped.get("token", []))
    assert "根据知识库内容" in tokens

    detail = await client.get(
        f"/api/sessions/{grouped['done'][0]['session_id']}", headers=admin_headers
    )
    assistant = [
        m for m in detail.json()["data"]["messages"] if m["role"] == "assistant"
    ][-1]
    assert assistant["intent"] == "policy_query"
    assert assistant["cited_chunk_ids"]


@pytest.mark.asyncio
async def test_complaint_creates_ticket(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4C_{uuid.uuid4().hex[:8]}")
    events = await chat_events(
        client, admin_headers, {"kb_ids": [kb["id"]], "message": "我要投诉！"}
    )
    grouped = events_dict(events)
    done = grouped["done"][0]
    assert done["intent"] == "complaint"
    assert re.match(r"^TK\d{14}[a-z0-9]{6}$", done["ticket_no"])
    session_id = done["session_id"]

    detail = await client.get(f"/api/sessions/{session_id}", headers=admin_headers)
    data = detail.json()["data"]
    assert data["session"]["status"] == "transferred"
    system_msgs = [m for m in data["messages"] if m["role"] == "system"]
    assert any(done["ticket_no"] in m["content"] for m in system_msgs)


@pytest.mark.asyncio
async def test_fallback_twice_escalates(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4B_{uuid.uuid4().hex[:8]}")
    events1 = await chat_events(
        client, admin_headers, {"kb_ids": [kb["id"]], "message": "哈哈哈哈哈哈"}
    )
    grouped1 = events_dict(events1)
    assert grouped1["done"][0]["intent"] == "other"
    assert grouped1["done"][0]["ticket_no"] is None
    session_id = grouped1["done"][0]["session_id"]

    events2 = await chat_events(
        client,
        admin_headers,
        {"session_id": session_id, "kb_ids": [kb["id"]], "message": "哈哈哈哈哈哈"},
    )
    grouped2 = events_dict(events2)
    assert grouped2["done"][0]["intent"] == "other"
    assert grouped2["done"][0]["ticket_no"]

    detail = await client.get(f"/api/sessions/{session_id}", headers=admin_headers)
    assert detail.json()["data"]["session"]["status"] == "transferred"


@pytest.mark.asyncio
async def test_transferred_session_blocks_chat(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4T_{uuid.uuid4().hex[:8]}")
    events = await chat_events(
        client, admin_headers, {"kb_ids": [kb["id"]], "message": "转人工"}
    )
    session_id = events_dict(events)["done"][0]["session_id"]
    events2 = await chat_events(
        client,
        admin_headers,
        {"session_id": session_id, "kb_ids": [kb["id"]], "message": "再问一句"},
    )
    grouped2 = events_dict(events2)
    assert "error" in grouped2
    assert grouped2["error"][0]["code"] == "40000"


@pytest.mark.asyncio
async def test_feedback_three_actions(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4FB_{uuid.uuid4().hex[:8]}")
    events = await chat_events(
        client,
        admin_headers,
        {"kb_ids": [kb["id"]], "message": "退款审核多久到账？"},
    )
    grouped = events_dict(events)
    citations = grouped["citations"][0]["citations"]
    assert citations
    session_id = grouped["done"][0]["session_id"]
    detail = await client.get(f"/api/sessions/{session_id}", headers=admin_headers)
    assistant = [
        m for m in detail.json()["data"]["messages"] if m["role"] == "assistant"
    ][-1]
    chunk_id = citations[0]["chunk_id"]

    for action in ("delete", "invalid", "add"):
        payload = {
            "session_id": session_id,
            "message_id": assistant["id"],
            "chunk_id": chunk_id,
            "action": action,
            "reason": "测试原因" if action == "invalid" else None,
        }
        resp = await client.post("/api/feedbacks", headers=admin_headers, json=payload)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["action"] == action

    # 非法 action → 422
    bad = await client.post(
        "/api/feedbacks",
        headers=admin_headers,
        json={
            "session_id": session_id,
            "message_id": assistant["id"],
            "chunk_id": chunk_id,
            "action": "unknown",
        },
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_sessions_list_recovery(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4S_{uuid.uuid4().hex[:8]}")
    await chat_events(
        client,
        admin_headers,
        {"kb_ids": [kb["id"]], "message": "商品签收后几天可以退货？"},
    )
    listing = await client.get("/api/sessions?page=1&page_size=10", headers=admin_headers)
    assert listing.status_code == 200
    data = listing.json()["data"]
    assert data["total"] >= 1
    assert all("kb_ids" in item for item in data["items"])


@pytest.mark.asyncio
async def test_intent_rules_configurable(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B4R_{uuid.uuid4().hex[:8]}")
    resp = await client.put(
        "/api/settings/intent",
        headers=admin_headers,
        json={"keywords": {"policy_query": ["天气测试词"]}},
    )
    assert resp.status_code == 200
    events = await chat_events(
        client, admin_headers, {"kb_ids": [kb["id"]], "message": "天气测试词是啥"}
    )
    assert events_dict(events)["done"][0]["intent"] == "policy_query"


@pytest.mark.asyncio
async def test_model_profiles_admin_only(client: AsyncClient, user_headers, admin_headers):
    viewer = await user_headers("viewer")
    resp = await client.get("/api/settings/model-profiles", headers=viewer)
    assert resp.status_code == 403

    profiles = await client.get("/api/settings/model-profiles", headers=admin_headers)
    assert profiles.status_code == 200
    items = profiles.json()["data"]
    assert items
    assert items[0]["api_key"] == "" or items[0]["api_key"].startswith("sk-***")

    activate = await client.put(
        f"/api/settings/model-profiles/{items[0]['id']}/activate",
        headers=admin_headers,
    )
    assert activate.status_code == 200


@pytest.mark.asyncio
async def test_chat_rbac(client: AsyncClient, user_headers):
    viewer = await user_headers("viewer")
    resp = await client.post(
        "/api/chat",
        headers=viewer,
        json={"kb_ids": [str(uuid.uuid4())], "message": "测试"},
    )
    assert resp.status_code == 403

