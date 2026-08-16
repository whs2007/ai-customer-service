"""速率限制单元测试（内存窗口兜底，无需数据库/Redis）。"""

from __future__ import annotations

import pytest
from app.core.exceptions import TooManyRequestsError
from app.core.ratelimit import check_rate_limit


@pytest.mark.asyncio
async def test_memory_window_allows_under_limit() -> None:
    await check_rate_limit("rl-test-allow", limit=3)
    await check_rate_limit("rl-test-allow", limit=3)


@pytest.mark.asyncio
async def test_memory_window_blocks_over_limit() -> None:
    key = "rl-test-block"
    for _ in range(2):
        await check_rate_limit(key, limit=2)
    with pytest.raises(TooManyRequestsError):
        await check_rate_limit(key, limit=2)


@pytest.mark.asyncio
async def test_zero_limit_disables_check() -> None:
    # limit <= 0 视为关闭
    await check_rate_limit("rl-test-off", limit=0)
    await check_rate_limit("rl-test-off", limit=0)


def test_too_many_requests_error_shape() -> None:
    exc = TooManyRequestsError()
    assert exc.http_status == 429
    assert exc.code == 42900
