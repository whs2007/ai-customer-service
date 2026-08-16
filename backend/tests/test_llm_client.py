"""LLM 客户端单元测试：ModelProfile 参数注入与全局回退（MockTransport，无需网络/DB）。"""

from __future__ import annotations

import json

import httpx
import pytest
from app.agents.llm import LLMClient
from app.core.config import Settings


def _sse_response(text: str) -> httpx.Response:
    return httpx.Response(200, text=text)


SSE_BODY = (
    'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
    "data: [DONE]\n"
)


@pytest.mark.asyncio
async def test_llm_client_uses_profile_parameters() -> None:
    """profile 注入的 base_url/api_key/temperature/max_tokens 必须真实生效。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return _sse_response(SSE_BODY)

    settings = Settings(
        environment="test",
        jwt_secret="s" * 32,
        llm_api_key="global-key",
        llm_base_url="https://global.example/v1",
    )
    client = LLMClient(
        settings,
        base_url="https://profile.example/v1",
        api_key="profile-key",
        temperature=0.2,
        max_tokens=128,
        transport=httpx.MockTransport(handler),
    )
    assert client.available is True

    chunks = []
    async for chunk in client.stream_chat(
        [{"role": "user", "content": "问题"}], model="glm-4"
    ):
        chunks.append(chunk)

    assert "".join(chunks) == "你好"
    assert captured["url"] == "https://profile.example/v1/chat/completions"
    assert captured["auth"] == "Bearer profile-key"
    body = captured["body"]
    assert body["model"] == "glm-4"
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == 128
    # token 估算已记录，供 trace_logs.tokens 落库
    assert client.last_usage is not None
    assert client.last_usage["completion_tokens"] >= 2
    assert client.last_usage["prompt_tokens"] >= 1


@pytest.mark.asyncio
async def test_llm_client_falls_back_to_global_config() -> None:
    """未注入 profile 时使用全局 llm_base_url/llm_api_key（兼容原行为）。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return _sse_response(SSE_BODY)

    settings = Settings(
        environment="test",
        jwt_secret="s" * 32,
        llm_api_key="global-key",
        llm_base_url="https://global.example/v1",
    )
    client = LLMClient(settings, transport=httpx.MockTransport(handler))
    async for _ in client.stream_chat(
        [{"role": "user", "content": "问题"}], model="glm-4"
    ):
        pass

    assert captured["url"] == "https://global.example/v1/chat/completions"
    assert captured["auth"] == "Bearer global-key"


@pytest.mark.asyncio
async def test_llm_client_mock_when_no_key() -> None:
    """无任何 key 时走 mock 流式（离线开发兜底）。"""
    settings = Settings(
        environment="test",
        jwt_secret="s" * 32,
        llm_api_key="",
        llm_base_url="",
    )
    client = LLMClient(settings)
    assert client.available is False
    chunks = []
    async for chunk in client.stream_chat(
        [{"role": "user", "content": "你好世界"}], model="glm-4"
    ):
        chunks.append(chunk)
    assert "".join(chunks) == "你好世界"


@pytest.mark.asyncio
async def test_llm_client_retries_transient_errors() -> None:
    """5xx 类瞬时错误应自动重试并最终成功（指数退避）。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="upstream boom")
        return _sse_response(SSE_BODY)

    settings = Settings(
        environment="test",
        jwt_secret="s" * 32,
        llm_api_key="k",
        llm_max_retries=2,
        llm_retry_base_delay=0.01,
    )
    client = LLMClient(settings, transport=httpx.MockTransport(handler))
    chunks = []
    async for chunk in client.stream_chat(
        [{"role": "user", "content": "问题"}], model="glm-4"
    ):
        chunks.append(chunk)
    assert "".join(chunks) == "你好"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_llm_client_does_not_retry_client_errors() -> None:
    """4xx（除 429）为调用方错误，不重试直接抛错。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    settings = Settings(
        environment="test",
        jwt_secret="s" * 32,
        llm_api_key="k",
        llm_max_retries=2,
        llm_retry_base_delay=0.01,
    )
    client = LLMClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        async for _ in client.stream_chat(
            [{"role": "user", "content": "问题"}], model="glm-4"
        ):
            pass
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_llm_client_gives_up_after_retries() -> None:
    """持续 5xx 时重试耗尽后抛出（供上层降级处理）。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    settings = Settings(
        environment="test",
        jwt_secret="s" * 32,
        llm_api_key="k",
        llm_max_retries=1,
        llm_retry_base_delay=0.01,
    )
    client = LLMClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        async for _ in client.stream_chat(
            [{"role": "user", "content": "问题"}], model="glm-4"
        ):
            pass
    assert calls["n"] == 2
