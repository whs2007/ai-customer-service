"""事件总线（11 §9 / 开发文档 01 §7）：进程内 EventBus + Redis pub/sub 预留。

订阅端点 /api/stream/events 按 scope 过滤；本模块负责事件发布与分发。
多实例部署时切换 Redis pub/sub（channel=cs:events），接口不变。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.redis import get_redis_client

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

REDIS_EVENT_CHANNEL = "cs:events"


class Subscriber:
    """单个 SSE 订阅者：scope + user_id + 事件队列（+ 可选自定义过滤）。"""

    def __init__(
        self,
        scope: str,
        user_id: str,
        queue: asyncio.Queue,
        extra_filter: Callable[[dict], bool] | None = None,
    ) -> None:
        self.scope = scope
        self.user_id = user_id
        self.queue = queue
        self.extra_filter = extra_filter


class EventBus:
    """事件总线：进程内投递 + Redis pub/sub 中继（审计 M10 修复）。

    单实例：本地直接投递；Redis 可用时同步 PUBLISH 到 cs:events。
    多实例：各实例启动 relay 订阅 cs:events，按 instance_id 跳过自己
    的广播，把远端事件交付给本地订阅者（scope 过滤不变）。
    """

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self.instance_id: str = str(uuid.uuid4())
        self._relay_task: asyncio.Task | None = None

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers = [
            s for s in self._subscribers if s.queue is not queue
        ]

    def publish(self, event: dict) -> None:
        """先本地投递，再广播到 Redis（供其它实例中继），事件带 instance_id 防回环。"""
        event = dict(event)
        event.setdefault("event_id", str(uuid.uuid4()))
        event.setdefault("created_at", datetime.now(UTC).isoformat())
        event.setdefault("instance_id", self.instance_id)
        self._deliver(event)
        # 无运行中事件循环（理论不出现）：放弃 Redis 广播，仅本地投递
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(self._redis_publish(event))

    def _deliver(self, event: dict) -> None:
        """向命中订阅条件的本地订阅者投递。"""
        for sub in list(self._subscribers):
            try:
                if not _scope_allows(sub, event):
                    continue
                if sub.extra_filter is not None and not sub.extra_filter(event):
                    continue
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # 慢消费者：丢弃该事件（SSE 断线重连后前端全量重拉兜底，11 §9.3）
                logger.warning(
                    "event_queue_full_dropped",
                    scope=sub.scope,
                    user_id=sub.user_id,
                    event_type=event.get("event"),
                )

    async def _redis_publish(self, event: dict) -> None:
        """异步 PUBLISH 到 Redis（失败仅告警，不影响本地投递）。"""
        redis = get_redis_client()
        if redis is None:
            return
        try:
            await redis.publish(
                REDIS_EVENT_CHANNEL,
                json.dumps(event, ensure_ascii=False, default=str),
            )
        except Exception:  # noqa: BLE001
            logger.warning("event_redis_publish_failed", event_type=event.get("event"))

    async def start_redis_relay(self) -> None:
        """启动 Redis 订阅中继：把其它实例广播的事件交付给本地订阅者。"""
        redis = get_redis_client()
        if redis is None:
            return
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(REDIS_EVENT_CHANNEL)
            logger.info("event_redis_relay_started", instance_id=self.instance_id)
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None or msg.get("type") != "message":
                    continue
                try:
                    event = json.loads(msg["data"])
                    if event.get("instance_id") == self.instance_id:
                        continue  # 跳过自己的广播（本地已直接投递）
                    self._deliver(event)
                except Exception:  # noqa: BLE001
                    logger.warning("event_redis_relay_parse_failed")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            # Redis 故障时降级为仅本地投递（单实例行为）
            logger.warning("event_redis_relay_stopped")
        finally:
            try:
                await pubsub.unsubscribe(REDIS_EVENT_CHANNEL)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001
                pass

    async def stop_redis_relay(self) -> None:
        if self._relay_task is not None and not self._relay_task.done():
            self._relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._relay_task
        self._relay_task = None


def _scope_allows(sub: Subscriber, event: dict) -> bool:
    """服务端 scope 权限过滤（开发文档 01 §7.3），严禁跨用户泄漏。"""
    event_type = event.get("event")
    if sub.scope == "admin":
        return True
    if sub.scope == "user":
        # 仅推送归属当前用户的会话/工单事件
        return str(event.get("user_id") or "") == str(sub.user_id)
    if sub.scope == "agent":
        # open 工单事件全员可见；已认领后仅 assignee 可见
        if event.get("ticket_status") == "open":
            return True
        return str(event.get("assignee_id") or "") == str(sub.user_id)
    logger.warning("unknown_event_scope", scope=sub.scope, event_type=event_type)
    return False


bus = EventBus()


async def start_event_relay() -> None:
    """应用生命周期启动：Redis 订阅中继任务（无 Redis 时为空操作）。"""
    bus._relay_task = asyncio.create_task(bus.start_redis_relay())


async def stop_event_relay() -> None:
    await bus.stop_redis_relay()


def publish_event(event_type: str, payload: dict) -> None:
    """发布事件（调用方保证数据已落库；同事件循环内投递，无需 await）。"""
    bus.publish({"event": event_type, **payload})


def event_payload(**kwargs: Any) -> dict:
    """构造标准事件负载（含幂等所需字段）。"""
    return kwargs
