"""实时事件流 SSE（11 §9 / 开发文档 01 §7）：scope 服务端权限过滤 + 20s 心跳。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, TooManyRequestsError
from app.core.metrics import SSE_CONNECTIONS, SSE_CONNECTIONS_TOTAL
from app.models.user import User
from app.services.event_service import Subscriber, bus

router = APIRouter(prefix="/stream", tags=["events"])

HEARTBEAT_SECONDS = 20
QUEUE_MAX_SIZE = 200
_active_queues: set[asyncio.Queue] = set()


@router.get("/events")
async def stream_events(
    scope: str = Query(default="user", pattern="^(user|agent|admin)$"),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE 事件订阅：按 scope 过滤（用户端/客服端/管理端）。"""
    if scope == "user" and user.role != "user":
        raise ForbiddenError("该订阅范围仅用户端可用")
    if scope == "agent" and user.role not in ("agent", "admin"):
        raise ForbiddenError("该订阅范围仅客服/管理员可用")
    if scope == "admin" and user.role != "admin":
        raise ForbiddenError("该订阅范围仅管理员可用")

    queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    # 【P1-4】连接上限：超出返回 429，防单实例连接数失控
    if len(_active_queues) >= get_settings().sse_max_connections:
        raise TooManyRequestsError("实时连接数已达上限，请稍后重试")
    _active_queues.add(queue)
    SSE_CONNECTIONS.inc()
    SSE_CONNECTIONS_TOTAL.inc()
    bus.subscribe(Subscriber(scope=scope, user_id=str(user.id), queue=queue))

    async def event_stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                    yield f"event: {item['event']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            _active_queues.discard(queue)
            SSE_CONNECTIONS.dec()
            bus.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
