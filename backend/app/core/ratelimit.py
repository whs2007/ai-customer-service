"""请求速率限制（08 §8：认证与 LLM 调用防滥用）。

固定窗口计数：优先使用 Redis（INCR + EXPIRE，天然跨实例一致）；
Redis 不可用时降级为进程内内存窗口（单实例兜底，日志不刷屏）。
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, TooManyRequestsError
from app.core.redis import get_redis_client

_memory_windows: dict[str, deque[float]] = defaultdict(deque)

# 算术验证码（MVP 内存实现，11 §3.2；多实例部署时迁移到 Redis）
_captcha_store: dict[str, dict] = {}
_CAPTCHA_TTL_SECONDS = 300
_CAPTCHA_MAX_FAILURES = 3


async def check_rate_limit(key: str, limit: int, window_seconds: float = 60.0) -> None:
    """限制 key 在窗口内的调用次数，超限抛 TooManyRequestsError。"""
    if not get_settings().rate_limit_enabled or limit <= 0:
        return

    redis = get_redis_client()
    if redis is not None:
        try:
            bucket = f"rl:{key}:{int(time.time()) // int(window_seconds)}"
            count = await redis.incr(bucket)
            if count == 1:
                await redis.expire(bucket, int(window_seconds) + 1)
            if count > limit:
                raise TooManyRequestsError("请求过于频繁，请稍后重试")
            return
        except TooManyRequestsError:
            raise
        except Exception:  # noqa: BLE001 - Redis 异常降级到内存窗口
            pass

    now = time.monotonic()
    # 【P2-4】进程内兜底窗口定期清理：删除空窗口与过期窗口，避免内存只增不减
    if len(_memory_windows) > 2048:
        for k in [
            k
            for k, w in _memory_windows.items()
            if not w or w[-1] <= now - max(window_seconds, 60.0)
        ]:
            _memory_windows.pop(k, None)
    window = _memory_windows[key]
    while window and window[0] <= now - window_seconds:
        window.popleft()
    if len(window) >= limit:
        raise TooManyRequestsError("请求过于频繁，请稍后重试")
    window.append(now)


def _client_ip(request) -> str:
    return request.client.host if request.client else "unknown"


async def enforce_login_rate_limit(request) -> None:
    settings = get_settings()
    await check_rate_limit(
        f"login:{_client_ip(request)}", settings.login_rate_per_minute
    )


async def enforce_refresh_rate_limit(request) -> None:
    settings = get_settings()
    await check_rate_limit(
        f"refresh:{_client_ip(request)}", settings.refresh_rate_per_minute
    )


async def enforce_chat_rate_limit(user) -> None:
    settings = get_settings()
    await check_rate_limit(f"chat:{user.id}", settings.chat_rate_per_minute)


async def enforce_register_rate_limit(request) -> None:
    """注册防刷：按 IP 每分钟 ≤ 5 次（12 §2.1）。"""
    settings = get_settings()
    await check_rate_limit(
        f"register:{_client_ip(request)}", settings.register_rate_per_minute
    )


def generate_captcha() -> tuple[str, str]:
    """生成算术验证码，返回 (challenge_id, 问题文本)。"""
    import random

    # 【修复 M6】生成时顺带清理过期验证码，避免内存只增不减
    now = time.monotonic()
    expired = [k for k, v in _captcha_store.items() if v["expires_at"] < now]
    for key in expired:
        _captcha_store.pop(key, None)

    a = random.randint(1, 9)
    b = random.randint(1, 9)
    op = random.choice(["+", "-"])
    answer = a + b if op == "+" else a - b
    challenge_id = f"cap:{uuid.uuid4().hex}"
    _captcha_store[challenge_id] = {
        "answer": str(answer),
        "expires_at": time.monotonic() + _CAPTCHA_TTL_SECONDS,
        "failures": 0,
    }
    return challenge_id, f"{a} {op} {b} = ?"


def verify_captcha(challenge_id: str, answer: str) -> None:
    """校验算术验证码；失败 3 次或超时则作废（12 §2.1）。"""
    if not challenge_id or not answer:
        raise BadRequestError("请输入验证码答案")
    item = _captcha_store.get(challenge_id)
    if item is None or item["expires_at"] < time.monotonic():
        _captcha_store.pop(challenge_id, None)
        raise BadRequestError("验证码已过期，请刷新后重试")
    if str(item["answer"]) != str(answer).strip():
        item["failures"] += 1
        if item["failures"] >= _CAPTCHA_MAX_FAILURES:
            _captcha_store.pop(challenge_id, None)
            raise BadRequestError("验证码错误次数过多，请刷新后重试")
        raise BadRequestError("验证码答案错误")
    _captcha_store.pop(challenge_id, None)
