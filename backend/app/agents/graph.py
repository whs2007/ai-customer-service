"""LangGraph 图组装（08 §4.4 图结构）。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    classify_intent,
    collect_form,
    escalate,
    fallback,
    generate,
    lookup_order,
    retrieve,
)
from app.agents.state import ChatState


def route_by_intent(state: ChatState) -> str:
    intent = state.get("intent", "other")
    if intent == "order_query":
        # 有订单号 → 工具查询；缺订单号 → 表单收集
        return "lookup_order" if state.get("order_no") else "collect_form"
    if intent == "policy_query":
        return "retrieve"
    if intent in ("complaint", "transfer"):
        return "escalate"
    return "fallback"


def after_fallback(state: ChatState) -> str:
    threshold = state.get("escalation_threshold", 2)
    return "escalate" if state.get("escalation_count", 0) >= threshold else END


def build_chat_graph():
    graph = StateGraph(ChatState)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("lookup_order", lookup_order)
    graph.add_node("collect_form", collect_form)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("escalate", escalate)
    graph.add_node("fallback", fallback)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges("classify_intent", route_by_intent)
    graph.add_edge("lookup_order", "generate")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    graph.add_edge("collect_form", END)
    graph.add_edge("escalate", END)
    graph.add_conditional_edges("fallback", after_fallback, {END: END, "escalate": "escalate"})
    return graph.compile()


chat_graph = build_chat_graph()
