"""B5 运营闭环测试：工单流转/筛选/命中片段、工作台口径、会话筛选/标注回流、RBAC。"""

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
        json={"name": name, "description": "B5 运营测试库"},
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


async def _chat(client: AsyncClient, headers, kb_id, message: str) -> dict:
    """发送消息并返回 done 事件数据。"""
    async with client.stream(
        "POST",
        "/api/chat",
        headers=headers,
        json={"kb_ids": [kb_id], "message": message},
    ) as resp:
        lines = [line.strip() async for line in resp.aiter_lines()]
    done = None
    for line in lines:
        if line.startswith("data:"):
            payload = json.loads(line[5:].strip())
            if "intent" in payload:
                done = payload
    assert done is not None
    return done


def _clear_dashboard_cache():
    from app.services import dashboard_service

    dashboard_service._cache.clear()


@pytest.mark.asyncio
async def test_ticket_flow_and_transition(
    client: AsyncClient, admin_headers, user_headers
):
    kb = await _make_kb(client, admin_headers, f"B5TK_{uuid.uuid4().hex[:8]}")
    done = await _chat(client, admin_headers, kb["id"], "我要投诉！")
    ticket_no = done["ticket_no"]
    assert ticket_no

    listing = await client.get(
        f"/api/tickets?keyword={ticket_no}", headers=admin_headers
    )
    assert listing.status_code == 200
    item = listing.json()["data"]["items"][0]
    assert item["ticket_no"] == ticket_no
    assert item["status"] == "open"

    # 工单写操作由客服账号执行（职责分离：管理端默认只读）
    agent_headers = await user_headers("agent")

    detail = await client.get(f"/api/tickets/{item['id']}", headers=admin_headers)
    d = detail.json()["data"]
    assert d["session_id"] == done["session_id"]
    assert d["notes"] == []

    # open → processing（start）
    start = await client.post(
        f"/api/tickets/{item['id']}/action",
        headers=agent_headers,
        json={"action": "start", "note": "开始处理投诉"},
    )
    assert start.status_code == 200
    assert start.json()["data"]["status"] == "processing"
    # 统一字段：start 需写入 claimed_at（与工作台认领一致）
    wb = (
        await client.get(f"/api/agent/tickets/{item['id']}", headers=admin_headers)
    ).json()["data"]
    assert wb["ticket"]["claimed_at"] is not None
    assert wb["ticket"]["assignee_id"] is not None

    # 重复 start → 400（状态机校验）
    again = await client.post(
        f"/api/tickets/{item['id']}/action",
        headers=agent_headers,
        json={"action": "start", "note": ""},
    )
    assert again.status_code == 400
    assert again.json()["code"] == 40000

    detail2 = await client.get(f"/api/tickets/{item['id']}", headers=admin_headers)
    notes = detail2.json()["data"]["notes"]
    assert len(notes) == 1
    assert notes[0]["status_from"] == "open"
    assert notes[0]["status_to"] == "processing"

    # processing → closed（close）
    close = await client.post(
        f"/api/tickets/{item['id']}/action",
        headers=agent_headers,
        json={"action": "close", "note": "已电话回访用户"},
    )
    assert close.status_code == 200
    assert close.json()["data"]["status"] == "closed"
    # 统一字段：close 需写入 closed_at 与 close_reason（与工作台关闭一致）
    wb2 = (
        await client.get(f"/api/agent/tickets/{item['id']}", headers=admin_headers)
    ).json()["data"]
    assert wb2["ticket"]["closed_at"] is not None
    assert wb2["ticket"]["close_reason"] == "已电话回访用户"
    detail3 = await client.get(f"/api/tickets/{item['id']}", headers=admin_headers)
    assert len(detail3.json()["data"]["notes"]) == 2

    # 非法 action → 参数校验 422
    bad = await client.post(
        f"/api/tickets/{item['id']}/action",
        headers=agent_headers,
        json={"action": "bad", "note": ""},
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_ticket_cited_chunks_display(
    client: AsyncClient, admin_headers, db_session
):
    kb = await _make_kb(client, admin_headers, f"B5CT_{uuid.uuid4().hex[:8]}")
    session_done = await _chat(client, admin_headers, kb["id"], "查询我的订单")
    session_id = uuid.UUID(session_done["session_id"])
    chunks = (
        await client.get(
            f"/api/knowledge-bases/{kb['id']}/documents", headers=admin_headers
        )
    ).json()["data"]["items"][0]["id"]
    chunks_list = (
        await client.get(f"/api/documents/{chunks}/chunks?page_size=5", headers=admin_headers)
    ).json()["data"]["items"]
    chunk_id = chunks_list[0]["id"]

    from app.agents.tools import create_ticket

    ticket = await create_ticket(
        db_session,
        session_id=session_id,
        content="测试命中片段",
        user_id=None,
        priority="medium",
        cited_chunk_ids=[chunk_id],
    )
    detail = await client.get(f"/api/tickets/{ticket.id}", headers=admin_headers)
    citations = detail.json()["data"]["citations"]
    assert len(citations) == 1
    assert citations[0]["chunk_id"] == chunk_id
    assert citations[0]["question"]
    assert citations[0]["document_name"].endswith(".xlsx")


@pytest.mark.asyncio
async def test_ticket_filters(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B5FL_{uuid.uuid4().hex[:8]}")
    done1 = await _chat(client, admin_headers, kb["id"], "我要投诉！")
    done2 = await _chat(client, admin_headers, kb["id"], "转人工处理")
    _clear_dashboard_cache()

    # 状态筛选
    opened = await client.get("/api/tickets?status=open", headers=admin_headers)
    assert opened.json()["data"]["total"] >= 2
    # 优先级：投诉 → high
    high = await client.get("/api/tickets?priority=high", headers=admin_headers)
    assert any(i["ticket_no"] == done1["ticket_no"] for i in high.json()["data"]["items"])
    # 关键词
    kw = await client.get(
        f"/api/tickets?keyword={done2['ticket_no']}", headers=admin_headers
    )
    assert kw.json()["data"]["total"] == 1
    # 时间范围（今日）
    from datetime import date

    today = date.today().isoformat()
    ranged = await client.get(
        f"/api/tickets?start_date={today}&end_date={today}", headers=admin_headers
    )
    assert ranged.json()["data"]["total"] >= 2


@pytest.mark.asyncio
async def test_dashboard_stats_and_charts(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B5DB_{uuid.uuid4().hex[:8]}")
    await _chat(client, admin_headers, kb["id"], "商品签收后几天可以退货？")  # 政策+引用
    await _chat(client, admin_headers, kb["id"], "我要投诉！")  # 转人工
    _clear_dashboard_cache()

    stats = (await client.get("/api/dashboard/stats", headers=admin_headers)).json()["data"]
    assert stats["today_sessions"] >= 2
    assert stats["transfer_count"] >= 1
    assert 0 <= stats["kb_hit_rate"] <= 100
    assert 0 <= stats["ai_solved_rate"] <= 100
    assert "policy_query" in stats["intent_distribution"]
    assert "complaint" in stats["intent_distribution"]

    trend = (await client.get("/api/dashboard/trend?days=7", headers=admin_headers)).json()["data"]
    assert len(trend) == 7
    assert trend[-1]["sessions"] >= 2

    intents = (await client.get("/api/dashboard/intents?days=7", headers=admin_headers)).json()["data"]
    intent_names = {i["intent"] for i in intents["items"]}
    assert "policy_query" in intent_names
    assert "complaint" in intent_names


@pytest.mark.asyncio
async def test_sessions_list_filters(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B5SF_{uuid.uuid4().hex[:8]}")
    policy_done = await _chat(client, admin_headers, kb["id"], "退款审核多久到账？")
    await _chat(client, admin_headers, kb["id"], "我要投诉！")

    # 关键词（消息内容）
    kw = await client.get(
        "/api/sessions?keyword=退款审核多久到账", headers=admin_headers
    )
    assert any(i["id"] == policy_done["session_id"] for i in kw.json()["data"]["items"])
    # 状态/是否转人工
    transferred = await client.get(
        "/api/sessions?transferred=true", headers=admin_headers
    )
    assert transferred.json()["data"]["total"] >= 1
    assert all(i["transferred"] for i in transferred.json()["data"]["items"])
    # 意图筛选
    policy = await client.get(
        "/api/sessions?intent=policy_query", headers=admin_headers
    )
    assert any(i["id"] == policy_done["session_id"] for i in policy.json()["data"]["items"])
    # 列表字段
    item = next(i for i in kw.json()["data"]["items"] if i["id"] == policy_done["session_id"])
    assert item["message_count"] >= 2
    assert item["intent"] == "policy_query"
    assert item["annotated"] is False


@pytest.mark.asyncio
async def test_session_detail_and_annotation_flow(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B5AN_{uuid.uuid4().hex[:8]}")
    policy_done = await _chat(client, admin_headers, kb["id"], "商品签收后几天可以退货？")
    sid = policy_done["session_id"]

    detail = (
        await client.get(f"/api/sessions/{sid}", headers=admin_headers)
    ).json()["data"]
    assert detail["trace"] is not None
    assert len(detail["trace"]["steps"]) >= 1
    assistant = next(m for m in detail["messages"] if m["role"] == "assistant")
    assert assistant["citations"]  # 引用明细
    assert detail["ticket"] is None
    assert detail["annotation"] is None

    # 标注（纳入评测集）
    annotate = await client.post(
        f"/api/sessions/{sid}/annotations",
        headers=admin_headers,
        json={
            "tags": ["退货", "示例"],
            "note": "高质量回答，纳入评测",
            "include_in_eval": True,
        },
    )
    assert annotate.status_code == 200
    assert annotate.json()["data"]["tags"] == ["退货", "示例"]

    # 详情带标注；候选出现（source=annotation）
    detail2 = (
        await client.get(f"/api/sessions/{sid}", headers=admin_headers)
    ).json()["data"]
    assert detail2["annotation"]["include_in_eval"] is True
    candidates = (
        await client.get("/api/evaluations/candidates", headers=admin_headers)
    ).json()["data"]
    assert any(c["source"] == "annotation" and c["source_id"] == sid for c in candidates)

    # 标注状态筛选
    annotated = await client.get(
        "/api/sessions?annotated=true", headers=admin_headers
    )
    assert any(i["id"] == sid for i in annotated.json()["data"]["items"])


@pytest.mark.asyncio
async def test_session_detail_ticket(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B5ST_{uuid.uuid4().hex[:8]}")
    done = await _chat(client, admin_headers, kb["id"], "转人工")
    detail = (
        await client.get(f"/api/sessions/{done['session_id']}", headers=admin_headers)
    ).json()["data"]
    assert detail["ticket"] is not None
    assert detail["ticket"]["ticket_no"] == done["ticket_no"]
    assert detail["session"]["status"] == "transferred"


@pytest.mark.asyncio
async def test_operations_rbac(client: AsyncClient, user_headers, admin_headers):
    viewer = await user_headers("viewer")
    agent = await user_headers("agent")
    kb = await _make_kb(client, admin_headers, f"B5RB_{uuid.uuid4().hex[:8]}")
    done = await _chat(client, admin_headers, kb["id"], "我要投诉")

    # viewer 只读
    # D1：viewer 仅 dashboard/帮助，会话/工单只读收敛为 403
    assert (await client.get("/api/tickets", headers=viewer)).status_code == 403
    assert (await client.get("/api/sessions", headers=viewer)).status_code == 403
    assert (await client.get("/api/dashboard/stats", headers=viewer)).status_code == 200
    tickets = (
        await client.get(
            "/api/tickets?keyword=" + done["ticket_no"], headers=admin_headers
        )
    ).json()["data"]["items"]
    action2 = await client.post(
        f"/api/tickets/{tickets[0]['id']}/action",
        headers=viewer,
        json={"action": "start", "note": ""},
    )
    assert action2.status_code == 403
    annotate = await client.post(
        f"/api/sessions/{done['session_id']}/annotations",
        headers=viewer,
        json={"tags": [], "note": "", "include_in_eval": False},
    )
    assert annotate.status_code == 403

    # agent 可处理工单
    action3 = await client.post(
        f"/api/tickets/{tickets[0]['id']}/action",
        headers=agent,
        json={"action": "start", "note": "agent 处理"},
    )
    assert action3.status_code == 200


@pytest.mark.asyncio
async def test_annotation_eval_set_admin_only(
    client: AsyncClient, user_headers, admin_headers
):
    """方案 C：客服标注不能指定评测集（403），仅产生候选；admin 可指定。"""
    kb = await _make_kb(client, admin_headers, f"CEVAL_{uuid.uuid4().hex[:8]}")
    done = await _chat(client, admin_headers, kb["id"], "商品签收后几天可以退货？")
    sid = done["session_id"]
    agent = await user_headers("agent")
    es = (
        await client.post(
            "/api/evaluations/sets",
            headers=admin_headers,
            json={"name": f"CEVALSET_{uuid.uuid4().hex[:6]}", "description": ""},
        )
    ).json()["data"]

    # agent 指定评测集 → 403
    r = await client.post(
        f"/api/sessions/{sid}/annotations",
        headers=agent,
        json={"tags": [], "note": "", "include_in_eval": True, "eval_set_id": es["id"]},
    )
    assert r.status_code == 403
    # agent 不带评测集 → 200（产生候选）
    r2 = await client.post(
        f"/api/sessions/{sid}/annotations",
        headers=agent,
        json={"tags": ["客服标注"], "note": "候选", "include_in_eval": True},
    )
    assert r2.status_code == 200
    # admin 可指定评测集
    r3 = await client.post(
        f"/api/sessions/{sid}/annotations",
        headers=admin_headers,
        json={"tags": [], "note": "admin 指定", "include_in_eval": True, "eval_set_id": es["id"]},
    )
    assert r3.status_code == 200
