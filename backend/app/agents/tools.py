"""Agent 工具（08 §4.4）：订单查询（MVP mock）、转人工建单。"""

from __future__ import annotations

import random
import string
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketPriority


def lookup_order_mock(order_no: str) -> dict:
    """订单/物流查询 MVP mock（08 §11 #5：MVP mock，后续对接真实系统）。"""
    return {
        "order_no": order_no,
        "status": "已签收",
        "carrier": "顺丰速运",
        "tracking_no": f"SF{random.randint(10**11, 10**12 - 1)}",
        "signed_at": "2026-08-10",
    }


def generate_ticket_no() -> str:
    """编号：TK + yyyyMMddHHmmss + 6 位随机（08 §4.5）。"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choices(string.digits + string.ascii_lowercase, k=6))
    return f"TK{timestamp}{suffix}"


async def create_ticket(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    content: str,
    user_id: uuid.UUID | None,
    priority: str = TicketPriority.MEDIUM.value,
    cited_chunk_ids: list[str] | None = None,
) -> Ticket:
    ticket = Ticket(
        ticket_no=generate_ticket_no(),
        session_id=session_id,
        user_id=user_id,
        content=content[:2000],
        priority=priority,
        cited_chunk_ids=cited_chunk_ids or [],
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket
