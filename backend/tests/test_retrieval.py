"""B3 检索测试：向量 / 混合 / 混合+重排（mock）/ 降级 / 标签过滤 / 多库 / 权限。"""

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


async def _make_kb_with_sample(client: AsyncClient, headers, name: str) -> dict:
    resp = await client.post(
        "/api/knowledge-bases",
        headers=headers,
        json={"name": name, "description": "B3 检索测试库"},
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


async def _search(client, headers, kb_ids, query, **overrides) -> dict:
    payload = {
        "kb_ids": kb_ids,
        "query": query,
        "top_k": 3,
        "retriever_mode": "hybrid",
        **overrides,
    }
    resp = await client.post("/api/retrieval/test", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class FakeRerank:
    """假重排客户端：分数与候选顺序反向，用于验证排序变化与 rerank_score 回填。"""

    available = True

    def __init__(self, settings=None):
        pass

    async def rerank(self, query, documents, top_n=None):
        return [float(i + 1) for i in range(len(documents))]


class UnavailableRerank(FakeRerank):
    available = False


@pytest.mark.asyncio
async def test_vector_mode(client: AsyncClient, admin_headers):
    kb = await _make_kb_with_sample(client, admin_headers, f"B3V_{uuid.uuid4().hex[:8]}")
    data = await _search(
        client, admin_headers, [kb["id"]], "商品签收后几天可以退货？",
        retriever_mode="vector",
    )
    assert data["actual_mode"] == "vector"
    assert data["rerank_skipped"] is False
    assert len(data["hits"]) == 3
    scores = [h["retrieval_score"] for h in data["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)
    first = data["hits"][0]
    assert first["document_name"].endswith(".xlsx")
    assert first["question"]
    assert first["retrieval_score"] >= scores[-1]


@pytest.mark.asyncio
async def test_hybrid_default_mode(client: AsyncClient, admin_headers):
    kb = await _make_kb_with_sample(client, admin_headers, f"B3H_{uuid.uuid4().hex[:8]}")
    data = await _search(client, admin_headers, [kb["id"]], "商品签收后几天可以退货？")
    assert data["actual_mode"] == "hybrid"
    assert data["retriever_mode"] == "hybrid"
    assert len(data["hits"]) == 3
    scores = [h["retrieval_score"] for h in data["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert all(h["rerank_score"] is None for h in data["hits"])


@pytest.mark.asyncio
async def test_hybrid_rerank_sorts_by_rerank_score(
    client: AsyncClient, admin_headers, monkeypatch
):
    monkeypatch.setattr("app.rag.retriever.RerankClient", FakeRerank)
    kb = await _make_kb_with_sample(client, admin_headers, f"B3R_{uuid.uuid4().hex[:8]}")
    data = await _search(
        client, admin_headers, [kb["id"]], "商品签收后几天可以退货？",
        retriever_mode="hybrid_rerank",
    )
    assert data["actual_mode"] == "hybrid_rerank"
    assert data["rerank_skipped"] is False
    assert len(data["hits"]) == 3
    rerank_scores = [h["rerank_score"] for h in data["hits"]]
    assert all(s is not None for s in rerank_scores)
    assert rerank_scores == sorted(rerank_scores, reverse=True)
    # 假重排分数与检索分反向 → 排序确实发生变化（可解释）
    retrieval_scores = [h["retrieval_score"] for h in data["hits"]]
    assert retrieval_scores == sorted(retrieval_scores, reverse=False)


@pytest.mark.asyncio
async def test_rerank_fallback_without_key(
    client: AsyncClient, admin_headers, monkeypatch
):
    monkeypatch.setattr("app.rag.retriever.RerankClient", UnavailableRerank)
    kb = await _make_kb_with_sample(client, admin_headers, f"B3F_{uuid.uuid4().hex[:8]}")
    data = await _search(
        client, admin_headers, [kb["id"]], "商品签收后几天可以退货？",
        retriever_mode="hybrid_rerank",
    )
    assert data["actual_mode"] == "hybrid"
    assert data["rerank_skipped"] is True
    assert all(h["rerank_score"] is None for h in data["hits"])


@pytest.mark.asyncio
async def test_tags_filter(client: AsyncClient, admin_headers):
    kb = await _make_kb_with_sample(client, admin_headers, f"B3T_{uuid.uuid4().hex[:8]}")
    data = await _search(
        client, admin_headers, [kb["id"]], "退货",
        tags=["退货"],
    )
    # 样例中带"退货"标签的为第 1、4 行
    expected = {"商品发货后几天可以退货？", "质量问题退货运费谁承担？"}
    assert {h["question"] for h in data["hits"]} <= expected
    assert data["hits"]


@pytest.mark.asyncio
async def test_multiple_kb_and_invalid_exclusion(
    client: AsyncClient, admin_headers
):
    kb1 = await _make_kb_with_sample(client, admin_headers, f"B3M1_{uuid.uuid4().hex[:8]}")
    kb2 = await _make_kb_with_sample(client, admin_headers, f"B3M2_{uuid.uuid4().hex[:8]}")
    fake_id = uuid.uuid4()
    data = await _search(
        client, admin_headers, [kb1["id"], kb2["id"], str(fake_id)],
        "退款审核多久到账？",
    )
    assert data["hits"]
    assert {h["kb_id"] for h in data["hits"]} <= {kb1["id"], kb2["id"]}

    # 全部无效 → 40000
    resp = await client.post(
        "/api/retrieval/test",
        headers=admin_headers,
        json={
            "kb_ids": [str(uuid.uuid4())],
            "query": "测试",
            "top_k": 3,
            "retriever_mode": "hybrid",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40000


@pytest.mark.asyncio
async def test_top_k_and_query_validation(client: AsyncClient, admin_headers):
    kb = await _make_kb_with_sample(client, admin_headers, f"B3V_{uuid.uuid4().hex[:8]}")
    # top_k 超范围 → 422
    resp = await client.post(
        "/api/retrieval/test",
        headers=admin_headers,
        json={"kb_ids": [str(kb["id"])], "query": "测试", "top_k": 11},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 42200
    # 空 query → 422
    resp2 = await client.post(
        "/api/retrieval/test",
        headers=admin_headers,
        json={"kb_ids": [str(kb["id"])], "query": ""},
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_retrieval_rbac(client: AsyncClient, user_headers):
    viewer = await user_headers("viewer")
    resp = await client.post(
        "/api/retrieval/test",
        headers=viewer,
        json={"kb_ids": [str(uuid.uuid4())], "query": "测试", "top_k": 3},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == 40300
