"""Redis 连接（08 §3.1 / §10）。

B1 阶段 Redis 仅做连接骨架：不可用时降级为告警，不阻塞应用启动；
B2 起 Celery 任务队列依赖 Redis，届时可调整启动策略。
"""

from __future__ import annotations

import asyncio
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import Request

from app.core.config import Settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_client: aioredis.Redis | None = None


async def init_redis(settings: Settings) -> None:
    global _client
    if settings.skip_redis:
        logger.warning("redis_skipped", reason="SKIP_REDIS=true（测试环境）")
        return
    try:
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            # Redis 5.0（Windows 版）仅支持 RESP2；redis-py 8.x 默认 RESP3（HELLO）会握手失败
            protocol=2,
        )
        await asyncio.wait_for(_client.ping(), timeout=1.0)
        logger.info("redis_connected", url=settings.redis_url)
    except Exception as exc:  # noqa: BLE001 - Redis 不可用时优雅降级
        _client = None
        logger.warning(
            "redis_unavailable",
            reason=str(exc),
            hint="B1 阶段 Redis 可选；B2 起为 Celery 依赖",
        )


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis_client() -> aioredis.Redis | None:
    return _client


async def get_redis(request: Request) -> Any:
    """FastAPI 依赖：返回 Redis 客户端（未连接时返回 None，由调用方降级）。"""
    return _client


async def ping_redis(timeout: float = 0.5) -> bool:
    if _client is None:
        return False
    try:
        await asyncio.wait_for(_client.ping(), timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False
