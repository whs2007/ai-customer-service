"""B4.5 应用评测测试：集 CRUD、30 条公开样例导入、任务执行与报告、
人工调通过、回流候选确认、eval_mode 不建单、RBAC。"""

from __future__ import annotations

import asyncio
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
        json={"name": name, "description": "B4.5 评测测试库"},
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


async def _create_set(client: AsyncClient, headers, name: str) -> dict:
    resp = await client.post(
        "/api/evaluations/sets",
        headers=headers,
        json={"name": name, "description": "B4.5 测试评测集"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _wait_task(client: AsyncClient, headers, task_id: str, timeout=120.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/evaluations/tasks/{task_id}", headers=headers)
        task = resp.json()["data"]
        if task["status"] in ("completed", "failed"):
            return task
        await asyncio.sleep(0.5)
    raise TimeoutError(f"评测任务超时: {task_id}")


@pytest.mark.asyncio
async def test_eval_set_crud(client: AsyncClient, admin_headers):
    name = f"EVALSET_{uuid.uuid4().hex[:8]}"
    es = await _create_set(client, admin_headers, name)
    assert es["name"] == name
    assert es["sample_count"] == 0

    dup = await client.post(
        "/api/evaluations/sets",
        headers=admin_headers,
        json={"name": name, "description": ""},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == 40900

    listing = await client.get("/api/evaluations/sets", headers=admin_headers)
    names = [item["name"] for item in listing.json()["data"]]
    assert name in names

    updated = await client.put(
        f"/api/evaluations/sets/{es['id']}",
        headers=admin_headers,
        json={"name": f"{name}_v2", "description": "更新"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == f"{name}_v2"

    deleted = await client.delete(f"/api/evaluations/sets/{es['id']}", headers=admin_headers)
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_import_public_samples(client: AsyncClient, admin_headers):
    es = await _create_set(client, admin_headers, f"PUB_{uuid.uuid4().hex[:8]}")
    resp = await client.post(
        f"/api/evaluations/sets/{es['id']}/samples/import-public",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert "30" in resp.json()["message"]

    samples = await client.get(
        f"/api/evaluations/sets/{es['id']}/samples?page_size=100",
        headers=admin_headers,
    )
    assert samples.json()["data"]["total"] == 30
    assert samples.json()["data"]["items"][0]["question"] == "商品签收后几天可以退货？"

    # 重复导入 → 409
    dup = await client.post(
        f"/api/evaluations/sets/{es['id']}/samples/import-public",
        headers=admin_headers,
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_batch_and_single_import(client: AsyncClient, admin_headers):
    es = await _create_set(client, admin_headers, f"IMP_{uuid.uuid4().hex[:8]}")
    single = await client.post(
        f"/api/evaluations/sets/{es['id']}/samples",
        headers=admin_headers,
        json={"question": "单条问题？", "expected_answer": "单条期望答案。"},
    )
    assert single.status_code == 200

    batch = await client.post(
        f"/api/evaluations/sets/{es['id']}/samples/import",
        headers=admin_headers,
        json={
            "items": [
                {"question": f"批量问题{i}", "expected_answer": f"批量答案{i}"}
                for i in range(3)
            ]
        },
    )
    assert batch.status_code == 200

    samples = await client.get(
        f"/api/evaluations/sets/{es['id']}/samples?page_size=10",
        headers=admin_headers,
    )
    assert samples.json()["data"]["total"] == 4


@pytest.mark.asyncio
async def test_run_task_report_and_no_ticket(
    client: AsyncClient, admin_headers, db_session
):
    from sqlalchemy import text

    kb = await _make_kb(client, admin_headers, f"EVALKB_{uuid.uuid4().hex[:8]}")
    es = await _create_set(client, admin_headers, f"TASK_{uuid.uuid4().hex[:8]}")
    await client.post(
        f"/api/evaluations/sets/{es['id']}/samples/import-public",
        headers=admin_headers,
    )

    before = await db_session.scalar(text("SELECT count(*) FROM tickets"))
    resp = await client.post(
        "/api/evaluations/tasks",
        headers=admin_headers,
        json={"eval_set_id": es["id"], "kb_ids": [kb["id"]]},
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()["data"]
    assert task["total"] == 30

    task = await _wait_task(client, admin_headers, task["id"])
    assert task["status"] == "completed", task.get("error_message")
    assert task["progress"] == 30
    assert task["score_avg"] is not None
    assert task["metrics"]["accuracy"] is not None

    report = await client.get(
        f"/api/evaluations/tasks/{task['id']}/report", headers=admin_headers
    )
    data = report.json()["data"]
    assert data["total"] == 30
    assert data["passed_count"] >= 0
    assert len(data["results"]) == 30
    first = data["results"][0]
    assert first["question"]
    assert first["expected_answer"]
    assert 0 <= first["scores"]["accuracy"] <= 100
    assert first["passed"] in (True, False)
    assert first["scores"]["relevancy"] is None
    assert first["scores"]["semantic"] is None

    # eval_mode：评测过程不产生真实工单
    after = await db_session.scalar(text("SELECT count(*) FROM tickets"))
    assert after == before


@pytest.mark.asyncio
async def test_pass_adjust_updates_stats(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"EVALADJ_{uuid.uuid4().hex[:8]}")
    es = await _create_set(client, admin_headers, f"ADJ_{uuid.uuid4().hex[:8]}")
    await client.post(
        f"/api/evaluations/sets/{es['id']}/samples/import-public",
        headers=admin_headers,
    )
    task = (
        await client.post(
            "/api/evaluations/tasks",
            headers=admin_headers,
            json={"eval_set_id": es["id"], "kb_ids": [kb["id"]]},
        )
    ).json()["data"]
    task = await _wait_task(client, admin_headers, task["id"])
    report = (
        await client.get(
            f"/api/evaluations/tasks/{task['id']}/report", headers=admin_headers
        )
    ).json()["data"]
    first = report["results"][0]
    current = first["passed"]

    resp = await client.put(
        f"/api/evaluations/results/{first['id']}/passed",
        headers=admin_headers,
        json={"passed": not current},
    )
    assert resp.status_code == 200

    report2 = (
        await client.get(
            f"/api/evaluations/tasks/{task['id']}/report", headers=admin_headers
        )
    ).json()["data"]
    # 切换通过状态：True→False 减 1，False→True 加 1（原公式在 current=True 时期望错误）
    delta = -1 if current else 1
    assert report2["passed_count"] == report["passed_count"] + delta


@pytest.mark.asyncio
async def test_candidate_feedback_flow(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"EVALFB_{uuid.uuid4().hex[:8]}")
    # 建立一次政策问答
    async with client.stream(
        "POST",
        "/api/chat",
        headers=admin_headers,
        json={"kb_ids": [kb["id"]], "message": "商品签收后几天可以退货？"},
    ) as resp:
        lines = [line.strip() async for line in resp.aiter_lines()]
    done_data = None
    for line in lines:
        if line.startswith("data:"):
            import json

            payload = json.loads(line[5:].strip())
            if payload.get("intent"):
                done_data = payload
    session_id = done_data["session_id"]
    detail = await client.get(f"/api/sessions/{session_id}", headers=admin_headers)
    assistant = [
        m for m in detail.json()["data"]["messages"] if m["role"] == "assistant"
    ][-1]

    fb = await client.post(
        "/api/feedbacks",
        headers=admin_headers,
        json={
            "session_id": session_id,
            "message_id": assistant["id"],
            "chunk_id": assistant["cited_chunk_ids"][0],
            "action": "invalid",
            "reason": "回答不准确，纳入评测",
            "include_in_eval": True,
        },
    )
    assert fb.status_code == 200

    candidates = await client.get("/api/evaluations/candidates", headers=admin_headers)
    items = candidates.json()["data"]
    target = next(c for c in items if c["question"] == "商品签收后几天可以退货？")
    assert target["source"] == "feedback"
    assert target["status"] == "pending"

    es = await _create_set(client, admin_headers, f"FLOW_{uuid.uuid4().hex[:8]}")
    confirm = await client.post(
        f"/api/evaluations/candidates/{target['id']}/confirm",
        headers=admin_headers,
        json={"eval_set_id": es["id"]},
    )
    assert confirm.status_code == 200
    samples = await client.get(
        f"/api/evaluations/sets/{es['id']}/samples?page_size=10",
        headers=admin_headers,
    )
    assert samples.json()["data"]["total"] == 1

    pending = await client.get("/api/evaluations/candidates", headers=admin_headers)
    assert target["id"] not in [c["id"] for c in pending.json()["data"]]


@pytest.mark.asyncio
async def test_candidate_reject(client: AsyncClient, admin_headers):
    # 直接构造一条候选（通过反馈标记生成）
    kb = await _make_kb(client, admin_headers, f"EVALRJ_{uuid.uuid4().hex[:8]}")
    async with client.stream(
        "POST",
        "/api/chat",
        headers=admin_headers,
        json={"kb_ids": [kb["id"]], "message": "退款审核多久到账？"},
    ) as resp:
        lines = [line.strip() async for line in resp.aiter_lines()]
    import json

    done_data = next(
        json.loads(line[5:].strip())
        for line in lines
        if line.startswith("data:") and "session_id" in line and "ticket_no" in line
    )
    session_id = done_data["session_id"]
    detail = await client.get(f"/api/sessions/{session_id}", headers=admin_headers)
    assistant = [
        m for m in detail.json()["data"]["messages"] if m["role"] == "assistant"
    ][-1]
    await client.post(
        "/api/feedbacks",
        headers=admin_headers,
        json={
            "session_id": session_id,
            "message_id": assistant["id"],
            "chunk_id": assistant["cited_chunk_ids"][0],
            "action": "invalid",
            "include_in_eval": True,
        },
    )
    candidates = (
        await client.get("/api/evaluations/candidates", headers=admin_headers)
    ).json()["data"]
    target = next(c for c in candidates if c["question"] == "退款审核多久到账？")
    reject = await client.post(
        f"/api/evaluations/candidates/{target['id']}/reject",
        headers=admin_headers,
    )
    assert reject.status_code == 200
    pending = (
        await client.get("/api/evaluations/candidates", headers=admin_headers)
    ).json()["data"]
    assert target["id"] not in [c["id"] for c in pending]


@pytest.mark.asyncio
async def test_evaluation_rbac(client: AsyncClient, user_headers):
    agent = await user_headers("agent")
    resp = await client.get("/api/evaluations/sets", headers=agent)
    assert resp.status_code == 403
    viewer = await user_headers("viewer")
    resp2 = await client.get("/api/evaluations/sets", headers=viewer)
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_judge_heuristic_deterministic():
    from app.services.judge_service import accuracy_heuristic, judge_answer

    s1 = await judge_answer("问题", "期望答案内容", "模型回答内容")
    s2 = await judge_answer("问题", "期望答案内容", "模型回答内容")
    assert s1 == s2
    assert 0 <= s1["accuracy"] <= 100
    assert s1["relevancy"] is None and s1["semantic"] is None
    # 完全一致 → 100
    assert accuracy_heuristic("完全相同的答案文本", "完全相同的答案文本") == 100.0
