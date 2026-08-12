"""对话图节点（08 §4.4）。"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from app.agents.intent import classify_intent as classify_by_rules
from app.agents.llm import LLMClient
from app.agents.state import ChatState
from app.agents.tools import create_ticket, lookup_order_mock
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.ticket import TicketPriority
from app.rag.retriever import run_retrieval_test
from app.services.settings_service import get_intent_rules

MOCK_STREAM_SLEEP = 0.01
MOCK_STREAM_SIZE = 6


def _emit(state: ChatState, event: str, data: dict) -> None:
    queue = state.get("queue")
    if queue is not None:
        queue.put_nowait({"event": event, "data": data})


async def _stream_text(state: ChatState, text: str) -> None:
    """逐块输出文本（mock 流式；真实 LLM 走 generate 节点的 LLMClient）。"""
    for i in range(0, len(text), MOCK_STREAM_SIZE):
        _emit(state, "token", {"content": text[i : i + MOCK_STREAM_SIZE]})
        await asyncio.sleep(MOCK_STREAM_SLEEP)


def _trace(state: ChatState, step: str, latency_ms: int, detail: dict | None = None) -> list[dict]:
    return state.get("trace", []) + [
        {"step": step, "latency_ms": latency_ms, **(detail or {})}
    ]


async def classify_intent(state: ChatState) -> dict:
    start = time.perf_counter()
    text = state["messages"][-1]["content"]
    async with get_session_factory()() as db:
        rules = await get_intent_rules(db)
    intent, order_no = classify_by_rules(text, rules)
    return {
        "intent": intent,
        "order_no": order_no,
        "trace": _trace(state, "intent", int((time.perf_counter() - start) * 1000), {"intent": intent}),
    }


async def lookup_order(state: ChatState) -> dict:
    start = time.perf_counter()
    info = lookup_order_mock(state.get("order_no") or "")
    return {
        "order_info": info,
        "trace": _trace(state, "order_lookup", int((time.perf_counter() - start) * 1000)),
    }


async def collect_form(state: ChatState) -> dict:
    """订单查询缺订单号：发表单卡片（08 §4.4 collect_form 新增）。"""
    start = time.perf_counter()
    form = {
        "fields": [
            {
                "name": "order_no",
                "label": "订单号",
                "type": "text",
                "required": True,
                "pattern": r"^\d{15}$",
                "message": "请输入 15 位数字订单号",
            },
            {
                "name": "contact",
                "label": "联系方式",
                "type": "text",
                "required": False,
                "pattern": r"^1\d{10}$",
                "message": "请输入 11 位手机号",
            },
        ]
    }
    _emit(state, "form", form)
    text = "查询订单需要提供订单号，请填写下方表单。"
    await _stream_text(state, text)
    return {
        "answer": text,
        "trace": _trace(state, "collect_form", int((time.perf_counter() - start) * 1000)),
    }


async def retrieve(state: ChatState) -> dict:
    """RAG 检索（多知识库 kb_ids，08 §4.4 retrieve 节点）。"""
    start = time.perf_counter()
    query = state["messages"][-1]["content"]
    async with get_session_factory()() as db:
        data = await run_retrieval_test(
            db,
            kb_ids=[uuid.UUID(x) for x in state["kb_ids"]],
            query=query,
            top_k=3,
            tags=[],
            retriever_mode="hybrid",
        )
    citations = data["hits"]
    return {
        "citations": citations,
        "trace": _trace(
            state, "retrieval", int((time.perf_counter() - start) * 1000),
            {"hits": len(citations), "kb_ids": state["kb_ids"]},
        ),
    }


async def generate(state: ChatState) -> dict:
    """生成回答（真实 LLM 或模板化 mock），逐块流式输出。"""
    start = time.perf_counter()
    intent = state.get("intent", "other")
    text = ""
    client = LLMClient(get_settings())

    if client.available:
        system_prompt = (
            "你是 AI 智能客服，回答需基于知识库引用，不得编造。"
            "引用来源用 [1][2] 编号标注。"
        )
        prompt_messages: list[dict] = [{"role": "system", "content": system_prompt}]
        prompt_messages.extend(state["messages"])
        if state.get("citations"):
            context = "\n".join(
                f"[{i + 1}] {c['question']}: {c['answer']}"
                for i, c in enumerate(state["citations"])
            )
            prompt_messages.append({"role": "user", "content": f"知识库片段：\n{context}"})
        chunks: list[str] = []
        async for chunk in client.stream_chat(prompt_messages, model=state.get("model_name", "")):
            chunks.append(chunk)
            _emit(state, "token", {"content": chunk})
        text = "".join(chunks)
    elif intent == "order_query":
        info = state.get("order_info") or {}
        text = (
            f"已为您查询订单 {info.get('order_no', '')}：状态为 {info.get('status', '')}"
            f"（签收日期 {info.get('signed_at', '')}），承运商 {info.get('carrier', '')}，"
            f"运单号 {info.get('tracking_no', '')}。"
        )
        await _stream_text(state, text)
    else:
        citations = state.get("citations") or []
        if citations:
            text = f"根据知识库内容：{citations[0]['answer']}"
            if len(citations) > 1:
                refs = "".join(f"[{i + 1}]" for i in range(len(citations)))
                text += f"\n\n参考来源：{refs}"
        else:
            text = "未在知识库中找到相关内容，建议转人工客服。"
        await _stream_text(state, text)

    return {
        "answer": text,
        "trace": _trace(state, "generate", int((time.perf_counter() - start) * 1000)),
    }


async def escalate(state: ChatState) -> dict:
    """转人工：创建工单（08 §4.4 escalate 节点）。"""
    start = time.perf_counter()
    last_user = next(
        (m["content"] for m in reversed(state["messages"]) if m["role"] == "user"),
        "",
    )
    priority = (
        TicketPriority.HIGH.value
        if state.get("intent") == "complaint"
        else TicketPriority.MEDIUM.value
    )
    async with get_session_factory()() as db:
        ticket = await create_ticket(
            db,
            session_id=uuid.UUID(state["session_id"]),
            content=last_user,
            user_id=uuid.UUID(state["user_id"]) if state.get("user_id") else None,
            priority=priority,
        )
    ticket_dict: dict[str, Any] = {
        "id": str(ticket.id),
        "ticket_no": ticket.ticket_no,
        "status": ticket.status,
        "priority": ticket.priority,
    }
    return {
        "ticket": ticket_dict,
        "trace": _trace(state, "escalate", int((time.perf_counter() - start) * 1000)),
    }


async def fallback(state: ChatState) -> dict:
    """兜底话术（08 §4.4 fallback 节点），escalation_count + 1。"""
    start = time.perf_counter()
    count = state.get("escalation_count", 0) + 1
    text = "抱歉，我暂时无法回答这个问题。您可以尝试换个问法，或转人工客服。"
    await _stream_text(state, text)
    return {
        "escalation_count": count,
        "answer": text,
        "trace": _trace(state, "fallback", int((time.perf_counter() - start) * 1000)),
    }

