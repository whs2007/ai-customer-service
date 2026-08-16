"""对话节点降级测试：LLM 故障时生成节点回退模板回答（无需 DB/网络）。"""

from __future__ import annotations

import pytest
from app.agents import nodes
from app.agents.graph import route_by_intent


def test_route_by_intent_other_goes_to_retrieve() -> None:
    """非订单/投诉/转人工的意图一律先检索，检索不到再兜底。"""
    assert route_by_intent({"intent": "other"}) == "retrieve"
    assert route_by_intent({"intent": "policy_query"}) == "retrieve"
    assert route_by_intent({"intent": "complaint"}) == "escalate"
    assert route_by_intent({"intent": "transfer"}) == "escalate"
    assert (
        route_by_intent({"intent": "order_query", "order_no": None})
        == "collect_form"
    )
    assert (
        route_by_intent({"intent": "order_query", "order_no": "123"})
        == "lookup_order"
    )


class FailingLLM:
    """模拟 LLM 完全不可用。"""

    available = True

    def __init__(self, settings):
        self.last_usage = None

    async def stream_chat(self, messages, model=""):
        raise RuntimeError("upstream down")
        yield  # pragma: no cover - 使方法成为异步生成器，迭代时抛错


class PartialLLM:
    """模拟生成中途断流。"""

    available = True

    def __init__(self, settings):
        self.last_usage = None

    async def stream_chat(self, messages, model=""):
        yield "部分回答"
        raise RuntimeError("stream cut")


@pytest.mark.asyncio
async def test_generate_falls_back_to_template(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "LLMClient", FailingLLM)
    state = {
        "intent": "other",
        "messages": [{"role": "user", "content": "问题"}],
        "citations": [],
        "trace": [],
        "queue": None,
    }
    result = await nodes.generate(state)
    assert "未在知识库中找到相关内容" in result["answer"]
    assert any(t["step"] == "generate" for t in result["trace"])


@pytest.mark.asyncio
async def test_generate_keeps_partial_and_marks_interrupted(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "LLMClient", PartialLLM)
    state = {
        "intent": "policy_query",
        "messages": [{"role": "user", "content": "问题"}],
        "citations": [],
        "trace": [],
        "queue": None,
    }
    result = await nodes.generate(state)
    assert result["answer"].startswith("部分回答")
    assert "生成中断" in result["answer"]
