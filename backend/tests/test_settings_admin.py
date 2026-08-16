"""B6a 系统设置与数据管理测试：用户管理、审计日志、配置读写与生效、
知识库可见性、重建/导出、RBAC。"""

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
        json={"name": name, "description": "B6a 设置测试库"},
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


async def _chat_done(client: AsyncClient, headers, kb_id, message: str) -> dict:
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


@pytest.mark.asyncio
async def test_user_management(client: AsyncClient, admin_headers):
    username = f"b6a_{uuid.uuid4().hex[:6]}"
    created = await client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": username,
            "password": "pass123456",
            "display_name": "测试用户",
            "role": "viewer",
            "status": "active",
        },
    )
    assert created.status_code == 200
    user_id = created.json()["data"]["id"]
    assert created.json()["data"]["role"] == "viewer"

    # 重复用户名 → 409
    dup = await client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": username, "password": "pass123456", "display_name": "x"},
    )
    assert dup.status_code == 409

    # 编辑角色/状态
    updated = await client.put(
        f"/api/auth/users/{user_id}",
        headers=admin_headers,
        json={"role": "agent", "status": "disabled"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["role"] == "agent"
    assert updated.json()["data"]["status"] == "disabled"

    # 重置密码后可用新密码登录（先启用）
    await client.put(
        f"/api/auth/users/{user_id}",
        headers=admin_headers,
        json={"status": "active"},
    )
    reset = await client.put(
        f"/api/auth/users/{user_id}/password",
        headers=admin_headers,
        json={"password": "newpass888"},
    )
    assert reset.status_code == 200
    login = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "newpass888"},
    )
    assert login.status_code == 200

    # 停用自己 → 400
    me = (await client.get("/api/auth/me", headers=admin_headers)).json()["data"]
    bad = await client.put(
        f"/api/auth/users/{me['id']}",
        headers=admin_headers,
        json={"status": "disabled"},
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_audit_logs(client: AsyncClient, admin_headers):
    await client.get("/api/auth/users", headers=admin_headers)
    listing = await client.get("/api/audit-logs?page_size=10", headers=admin_headers)
    assert listing.status_code == 200
    data = listing.json()["data"]
    assert data["total"] >= 1
    actions = {item["action"] for item in data["items"]}
    assert "login" in actions

    filtered = await client.get("/api/audit-logs?action=login", headers=admin_headers)
    assert filtered.json()["data"]["total"] >= 1


@pytest.mark.asyncio
async def test_prompt_and_escalation_config_effect(
    client: AsyncClient, admin_headers
):
    kb = await _make_kb(client, admin_headers, f"B6CFG_{uuid.uuid4().hex[:8]}")
    try:
        # 自定义兜底话术
        await client.put(
            "/api/settings/prompt",
            headers=admin_headers,
            json={"system_prompt": "测试人设", "fallback_text": "自定义兜底话术", "escalation_rule_text": "规则"},
        )
        done = await _chat_done(client, admin_headers, kb["id"], "哈哈哈哈哈哈")
        assert done["intent"] == "other"

        # 转人工阈值 = 1：一次兜底即转人工
        await client.put(
            "/api/settings/escalation",
            headers=admin_headers,
            json={"threshold": 1, "priority_rules": {"other": "low"}},
        )
        done2 = await _chat_done(client, admin_headers, kb["id"], "哈哈哈哈哈")
        assert done2["ticket_no"] is None
        # 明确要求转人工仍会建单
        done3 = await _chat_done(client, admin_headers, kb["id"], "转人工")
        assert done3["ticket_no"] is not None
    finally:
        # 恢复默认，避免影响其他测试
        await client.put(
            "/api/settings/prompt",
            headers=admin_headers,
            json={
                "system_prompt": "你是 AI 智能客服，回答需基于知识库引用，不得编造；引用来源用 [1][2] 编号标注。",
                "fallback_text": "抱歉，我暂时无法回答这个问题。您可以尝试换个问法，或转人工客服。",
                "escalation_rule_text": "连续 2 次无法回答或用户投诉/明确要求转人工时，转人工并创建工单。",
            },
        )
        await client.put(
            "/api/settings/escalation",
            headers=admin_headers,
            json={"threshold": 2, "priority_rules": {"complaint": "high", "transfer": "medium", "other": "medium"}},
        )


@pytest.mark.asyncio
async def test_chunking_config_effect(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B6CK_{uuid.uuid4().hex[:8]}")
    try:
        await client.put(
            "/api/settings/chunking",
            headers=admin_headers,
            json={"chunk_size": 200, "overlap": 20},
        )
        text = "分块测试内容。" * 100  # 800 字
        resp = await client.post(
            f"/api/knowledge-bases/{kb['id']}/documents",
            headers=admin_headers,
            files={"file": ("分块.txt", text.encode("utf-8"), "text/plain")},
        )
        doc = await _wait_document(client, admin_headers, resp.json()["data"]["document_id"])
        assert doc["status"] == "completed"
        chunks = (
            await client.get(
                f"/api/documents/{doc['id']}/chunks?page_size=50", headers=admin_headers
            )
        ).json()["data"]["items"]
        assert len(chunks) >= 2
        assert all(len(c["answer"]) <= 200 for c in chunks)
    finally:
        await client.put(
            "/api/settings/chunking",
            headers=admin_headers,
            json={"chunk_size": 500, "overlap": 50},
        )


@pytest.mark.asyncio
async def test_kb_visibility_for_agent(client: AsyncClient, user_headers, admin_headers):
    # 两个 agent：A 可见，B 不可见（visibility=user）
    suffix = uuid.uuid4().hex[:6]
    ua = (
        await client.post(
            "/api/auth/users",
            headers=admin_headers,
            json={"username": f"vis_a_{suffix}", "password": "pass123456", "display_name": "A", "role": "agent"},
        )
    ).json()["data"]
    await client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={"username": f"vis_b_{suffix}", "password": "pass123456", "display_name": "B", "role": "agent"},
    )
    headers_a = {
        "Authorization": "Bearer "
        + (
            await client.post(
                "/api/auth/login", json={"username": f"vis_a_{suffix}", "password": "pass123456"}
            )
        ).json()["data"]["access_token"]
    }
    headers_b = {
        "Authorization": "Bearer "
        + (
            await client.post(
                "/api/auth/login", json={"username": f"vis_b_{suffix}", "password": "pass123456"}
            )
        ).json()["data"]["access_token"]
    }

    name = f"B6VIS_{uuid.uuid4().hex[:8]}"
    kb = (
        await client.post(
            "/api/knowledge-bases",
            headers=admin_headers,
            json={"name": name, "description": ""},
        )
    ).json()["data"]
    await client.put(
        f"/api/knowledge-bases/{kb['id']}",
        headers=admin_headers,
        json={
            "name": name,
            "description": "",
            "visibility": "user",
            "visible_user_ids": [str(ua["id"])],
        },
    )
    list_a = (await client.get("/api/knowledge-bases", headers=headers_a)).json()["data"]
    list_b = (await client.get("/api/knowledge-bases", headers=headers_b)).json()["data"]
    assert any(k["name"] == name for k in list_a)
    assert not any(k["name"] == name for k in list_b)


@pytest.mark.asyncio
async def test_model_profiles_crud_default(client: AsyncClient, admin_headers):
    profiles = (
        await client.get("/api/settings/model-profiles", headers=admin_headers)
    ).json()["data"]
    if not any(p["is_default"] for p in profiles):
        # 测试库跨轮残留：无默认时先指定一个
        await client.put(
            f"/api/settings/model-profiles/{profiles[0]['id']}/activate",
            headers=admin_headers,
        )
        profiles = (
            await client.get("/api/settings/model-profiles", headers=admin_headers)
        ).json()["data"]
    default = next(p for p in profiles if p["is_default"])

    # 删除默认 → 400
    bad = await client.delete(
        f"/api/settings/model-profiles/{default['id']}", headers=admin_headers
    )
    assert bad.status_code == 400

    # 新增第二个对话 Profile 并设为默认
    created = await client.post(
        "/api/settings/model-profiles",
        headers=admin_headers,
        json={
            "name": f"测试模型_{uuid.uuid4().hex[:6]}",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "api_key": "",
            "role": "chat",
            "enabled": True,
        },
    )
    assert created.status_code == 200
    second = created.json()["data"]
    activate = await client.put(
        f"/api/settings/model-profiles/{second['id']}/activate", headers=admin_headers
    )
    assert activate.status_code == 200

    # 原默认现在可删除
    deleted = await client.delete(
        f"/api/settings/model-profiles/{default['id']}", headers=admin_headers
    )
    assert deleted.status_code == 200

    # 测试连通：无 Key 的 Profile 返回 ok=False 而不是崩溃
    test = await client.post(
        f"/api/settings/model-profiles/{second['id']}/test", headers=admin_headers
    )
    assert test.status_code == 200
    assert test.json()["data"]["ok"] is False
    assert "未配置 API Key" in test.json()["data"]["message"]


@pytest.mark.asyncio
async def test_rebuild_vectors_and_export(client: AsyncClient, admin_headers):
    kb = await _make_kb(client, admin_headers, f"B6RB_{uuid.uuid4().hex[:8]}")
    rebuild = await client.post("/api/admin/rebuild-vectors", headers=admin_headers)
    assert rebuild.status_code == 200
    data = rebuild.json()["data"]
    assert data["total"] >= 1
    assert data["succeeded"] >= 1

    export = await client.get("/api/admin/export", headers=admin_headers)
    assert export.status_code == 200
    body = json.loads(export.content.decode("utf-8"))
    assert any(kb_item["name"] == kb["name"] for kb_item in body["knowledge_bases"])


@pytest.mark.asyncio
async def test_settings_admin_rbac(client: AsyncClient, user_headers):
    agent = await user_headers("agent")
    viewer = await user_headers("viewer")
    assert (await client.get("/api/audit-logs", headers=agent)).status_code == 403
    assert (await client.get("/api/settings/prompt", headers=viewer)).status_code == 403
    assert (
        await client.put(
            "/api/settings/prompt",
            headers=agent,
            json={"system_prompt": "x", "fallback_text": "x", "escalation_rule_text": "x"},
        )
    ).status_code == 403
    assert (
        await client.post("/api/admin/rebuild-vectors", headers=viewer)
    ).status_code == 403
