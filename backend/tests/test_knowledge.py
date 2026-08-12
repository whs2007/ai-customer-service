"""B2 知识库冒烟测试：KB CRUD、上传解析、Chunk 管理、向量化、级联删除、RBAC。"""

from __future__ import annotations

import asyncio
import io
import time
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

SAMPLE_XLSX = (
    Path(__file__).resolve().parents[1] / "samples" / "FAQ知识库导入模板.xlsx"
)


async def _wait_document(
    client: AsyncClient,
    headers: dict[str, str],
    doc_id: str,
    timeout: float = 15.0,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/documents/{doc_id}", headers=headers)
        doc = resp.json()["data"]
        if doc["status"] in ("completed", "failed"):
            return doc
        await asyncio.sleep(0.2)
    raise TimeoutError(f"文档处理超时: {doc_id}")


async def _create_kb(client: AsyncClient, headers: dict[str, str], name: str) -> dict:
    resp = await client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": name, "description": "测试知识库"},
    )
    assert resp.status_code == 200
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_knowledge_base_crud(client: AsyncClient, admin_headers):
    name = f"KB_{uuid.uuid4().hex[:8]}"
    kb = await _create_kb(client, admin_headers, name)
    assert kb["name"] == name
    assert kb["doc_count"] == 0

    # 重复名称 → 40900
    dup = await client.post(
        "/api/knowledge-bases",
        headers=admin_headers,
        json={"name": name, "description": ""},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == 40900

    # 列表包含新库
    listing = await client.get("/api/knowledge-bases", headers=admin_headers)
    assert listing.status_code == 200
    names = [item["name"] for item in listing.json()["data"]]
    assert name in names

    # 更新
    updated = await client.put(
        f"/api/knowledge-bases/{kb['id']}",
        headers=admin_headers,
        json={"name": f"{name}_v2", "description": "更新描述"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == f"{name}_v2"

    # 删除（软删除）
    deleted = await client.delete(f"/api/knowledge-bases/{kb['id']}", headers=admin_headers)
    assert deleted.status_code == 200
    listing2 = await client.get("/api/knowledge-bases", headers=admin_headers)
    assert name not in [item["name"] for item in listing2.json()["data"]]
    missing = await client.get(f"/api/knowledge-bases/{kb['id']}", headers=admin_headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == 40400


@pytest.mark.asyncio
async def test_upload_xlsx_parse_and_vectorize(
    client: AsyncClient, admin_headers, db_session
):
    kb = await _create_kb(client, admin_headers, f"KB_{uuid.uuid4().hex[:8]}")
    with SAMPLE_XLSX.open("rb") as f:
        resp = await client.post(
            f"/api/knowledge-bases/{kb['id']}/documents",
            headers=admin_headers,
            files={
                "file": (
                    "FAQ知识库导入模板.xlsx",
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert resp.status_code == 200
    upload = resp.json()["data"]
    assert upload["file_name"] == "FAQ知识库导入模板.xlsx"
    assert upload["status"] == "uploading"

    doc = await _wait_document(client, admin_headers, upload["document_id"])
    assert doc["status"] == "completed", doc.get("error_message")
    assert doc["chunk_count"] == 6

    # Chunk 列表内容与 FAQ 模板一致（04 §4.6）
    chunks_resp = await client.get(
        f"/api/documents/{upload['document_id']}/chunks?page_size=50",
        headers=admin_headers,
    )
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()["data"]["items"]
    assert len(chunks) == 6
    assert chunks[0]["question"] == "商品发货后几天可以退货？"
    assert chunks[0]["tags"] == ["退货"]
    assert chunks[0]["category"] == "售后政策"
    assert chunks[0]["row"] == "2"
    assert chunks[2]["tags"] == ["退款", "虚拟商品"]

    # 向量已写入且维度为 1024
    from sqlalchemy import text

    dim = await db_session.scalar(
        text("SELECT vector_dims(embedding) FROM chunks WHERE doc_id = :d LIMIT 1"),
        {"d": upload["document_id"]},
    )
    assert dim == 1024


@pytest.mark.asyncio
async def test_upload_invalid_extension(client: AsyncClient, admin_headers):
    kb = await _create_kb(client, admin_headers, f"KB_{uuid.uuid4().hex[:8]}")
    resp = await client.post(
        f"/api/knowledge-bases/{kb['id']}/documents",
        headers=admin_headers,
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40000


@pytest.mark.asyncio
async def test_upload_corrupt_file_fails(client: AsyncClient, admin_headers):
    kb = await _create_kb(client, admin_headers, f"KB_{uuid.uuid4().hex[:8]}")
    resp = await client.post(
        f"/api/knowledge-bases/{kb['id']}/documents",
        headers=admin_headers,
        files={"file": ("bad.xlsx", io.BytesIO(b"this is not an xlsx"), "application/octet-stream")},
    )
    doc_id = resp.json()["data"]["document_id"]
    doc = await _wait_document(client, admin_headers, doc_id)
    assert doc["status"] == "failed"
    assert doc["error_message"]

    # 失败后可重新解析（重新解析同样失败但接口可用）
    reparse = await client.post(f"/api/documents/{doc_id}/reparse", headers=admin_headers)
    assert reparse.status_code == 200
    assert reparse.json()["data"]["status"] == "uploading"


@pytest.mark.asyncio
async def test_text_upload_chunking(client: AsyncClient, admin_headers):
    kb = await _create_kb(client, admin_headers, f"KB_{uuid.uuid4().hex[:8]}")
    text = "退换货政策说明。" * 200  # 8 字 × 200 = 1600 字单段 → 500/50 重叠切 4 段
    resp = await client.post(
        f"/api/knowledge-bases/{kb['id']}/documents",
        headers=admin_headers,
        files={"file": ("政策说明.txt", io.BytesIO(text.encode("utf-8")), "text/plain")},
    )
    doc = await _wait_document(client, admin_headers, resp.json()["data"]["document_id"])
    assert doc["status"] == "completed"
    assert doc["chunk_count"] == 4

    chunks_resp = await client.get(
        f"/api/documents/{doc['id']}/chunks?page_size=10", headers=admin_headers
    )
    chunks = chunks_resp.json()["data"]["items"]
    assert len(chunks) == 4
    assert len(chunks[0]["answer"]) <= 500
    # 重叠：第 2 段起始与第 1 段末尾 50 字一致
    assert chunks[1]["answer"].startswith(chunks[0]["answer"][-50:])


@pytest.mark.asyncio
async def test_chunk_manual_crud(client: AsyncClient, admin_headers, db_session):
    kb = await _create_kb(client, admin_headers, f"KB_{uuid.uuid4().hex[:8]}")
    with SAMPLE_XLSX.open("rb") as f:
        upload = await client.post(
            f"/api/knowledge-bases/{kb['id']}/documents",
            headers=admin_headers,
            files={"file": ("FAQ知识库导入模板.xlsx", f, "application/octet-stream")},
        )
    doc = await _wait_document(client, admin_headers, upload.json()["data"]["document_id"])

    # 新增
    created = await client.post(
        "/api/chunks",
        headers=admin_headers,
        json={
            "doc_id": doc["id"],
            "question": "人工新增问题？",
            "answer": "人工新增答案。",
            "tags": ["测试"],
            "page": "1",
        },
    )
    assert created.status_code == 200
    chunk = created.json()["data"]
    assert chunk["chunk_index"] == 7
    assert chunk["tags"] == ["测试"]
    assert chunk["word_count"] == len("人工新增答案。")

    # 编辑 → 重新向量化
    updated = await client.put(
        f"/api/chunks/{chunk['id']}",
        headers=admin_headers,
        json={"question": "编辑后的问题？", "answer": "编辑后的答案内容。"},
    )
    assert updated.status_code == 200
    assert updated.json()["message"] == "已更新，正在重新向量化"
    assert updated.json()["data"]["question"] == "编辑后的问题？"

    # 删除
    deleted = await client.delete(f"/api/chunks/{chunk['id']}", headers=admin_headers)
    assert deleted.status_code == 200
    detail = await client.get(f"/api/documents/{doc['id']}/chunks", headers=admin_headers)
    assert detail.json()["data"]["total"] == 6


@pytest.mark.asyncio
async def test_delete_knowledge_base_cascades(
    client: AsyncClient, admin_headers, db_session
):
    kb = await _create_kb(client, admin_headers, f"KB_{uuid.uuid4().hex[:8]}")
    with SAMPLE_XLSX.open("rb") as f:
        upload = await client.post(
            f"/api/knowledge-bases/{kb['id']}/documents",
            headers=admin_headers,
            files={"file": ("FAQ知识库导入模板.xlsx", f, "application/octet-stream")},
        )
    doc = await _wait_document(client, admin_headers, upload.json()["data"]["document_id"])
    assert doc["chunk_count"] == 6

    resp = await client.delete(f"/api/knowledge-bases/{kb['id']}", headers=admin_headers)
    assert resp.status_code == 200

    from sqlalchemy import text

    chunk_count = await db_session.scalar(
        text("SELECT count(*) FROM chunks WHERE kb_id = :kb"), {"kb": kb["id"]}
    )
    doc_count = await db_session.scalar(
        text("SELECT count(*) FROM documents WHERE kb_id = :kb AND deleted_at IS NULL"),
        {"kb": kb["id"]},
    )
    assert chunk_count == 0
    assert doc_count == 0


@pytest.mark.asyncio
async def test_knowledge_rbac(client: AsyncClient, user_headers):
    viewer = await user_headers("viewer")
    resp = await client.get("/api/knowledge-bases", headers=viewer)
    assert resp.status_code == 403
    assert resp.json()["code"] == 40300

    agent = await user_headers("agent")
    listing = await client.get("/api/knowledge-bases", headers=agent)
    assert listing.status_code == 200
    create = await client.post(
        "/api/knowledge-bases",
        headers=agent,
        json={"name": f"agent_kb_{uuid.uuid4().hex[:8]}", "description": ""},
    )
    assert create.status_code == 403


@pytest.mark.asyncio
async def test_mock_embedding_deterministic():
    from app.rag.embeddings import EmbeddingClient

    client_ = EmbeddingClient()
    v1 = await client_.embed_text("退货政策")
    v2 = await client_.embed_text("退货政策")
    v3 = await client_.embed_text("退款政策")
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == 1024
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_parser_faq_rows():
    from app.pipeline.parser import parse_tags

    assert parse_tags("退货, 退款，运费；投诉、物流") == ["退货", "退款", "运费", "投诉", "物流"]
    assert len(parse_tags(",".join([f"标签{i}" for i in range(15)]))) == 10
    assert parse_tags("") == []
