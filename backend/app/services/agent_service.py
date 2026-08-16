"""客服在线状态（13 §2.3 / 开发文档 01 §5.6）：内存实现，Redis 预留。"""

from __future__ import annotations

import time

from app.core.redis import get_redis_client

_ONLINE_TTL_SECONDS = 300
_memory_online: dict[str, float] = {}


async def set_online(user_id: str, online: bool) -> None:
    """设置客服在线/离线；有 Redis 时写入 agent:online:{user_id}（TTL 刷新）。"""
    redis = get_redis_client()
    if redis is not None:
        key = f"agent:online:{user_id}"
        try:
            if online:
                await redis.set(key, "1", ex=_ONLINE_TTL_SECONDS)
            else:
                await redis.delete(key)
            return
        except Exception:  # noqa: BLE001 - Redis 异常降级到内存
            pass
    if online:
        _memory_online[user_id] = time.monotonic()
    else:
        _memory_online.pop(user_id, None)


async def is_online(user_id: str) -> bool:
    redis = get_redis_client()
    if redis is not None:
        try:
            return bool(await redis.exists(f"agent:online:{user_id}"))
        except Exception:  # noqa: BLE001
            pass
    last = _memory_online.get(user_id)
    return last is not None and time.monotonic() - last < _ONLINE_TTL_SECONDS
