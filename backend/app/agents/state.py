"""ChatState 定义（08 §4.4）。"""

from __future__ import annotations

from typing import Any, TypedDict


class ChatState(TypedDict, total=False):
    """对话图状态。"""

    session_id: str
    user_id: str | None
    messages: list[dict]          # [{role, content}]
    intent: str                   # order_query / policy_query / complaint / transfer / other
    kb_ids: list[str]
    order_no: str | None
    form_data: dict | None        # 对话内表单收集结果（新增）
    escalation_count: int
    escalation_threshold: int           # 转人工阈值（settings 可配，默认 2）
    citations: list[dict]         # 知识引用片段
    order_info: dict | None       # 订单查询结果（MVP mock）
    ticket: dict | None           # 转人工工单
    model_profile_id: str | None
    eval_mode: bool                # 评测模式：转人工不真实建单（B4.5 新增）
    answer: str
    queue: Any                    # asyncio.Queue：SSE 事件中转
    trace: list[dict]             # 链路步骤（intent/retrieval/generate 耗时）
