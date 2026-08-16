"""LLM 客户端（08 §2：智谱 GLM 起步）。

配置 LLM_API_KEY 时调用 OpenAI 兼容 chat/completions（流式）；未配置时
使用模板化 mock 生成，保证离线可演示。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.metrics import LLM_CALLS, LLM_COST, LLM_FAILURES, LLM_TOKENS

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

MOCK_CHUNK_SIZE = 6
MOCK_CHUNK_DELAY = 0.02


class LLMClient:
    """LLM 客户端。

    支持从 ModelProfile 注入 base_url/api_key/temperature/max_tokens：
    未注入时回退全局配置（兼容原有单模型部署）。
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        transport: Any | None = None,
    ):
        self.settings = settings or get_settings()
        self._base_url = base_url
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._transport = transport  # 测试注入用
        self.last_usage: dict | None = None  # 最近一次调用的 token 估算（供 trace 落库）

    @property
    def api_key(self) -> str:
        return self._api_key or self.settings.llm_api_key

    @property
    def base_url(self) -> str:
        return (
            self._base_url
            or self.settings.llm_base_url
            or "https://open.bigmodel.cn/api/paas/v4"
        ).rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def stream_chat(
        self,
        messages: list[dict],
        model: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """按 token/chunk 流式返回生成文本。"""
        if self.available:
            self.last_usage = None
            async for chunk in self._stream_via_api(
                messages, model, temperature, max_tokens
            ):
                yield chunk
        else:
            # mock：整段文本按小块输出（无真实 LLM 时保持流式体验）
            self.last_usage = None
            text = messages[-1].get("content", "")
            for i in range(0, len(text), MOCK_CHUNK_SIZE):
                yield text[i : i + MOCK_CHUNK_SIZE]
                await asyncio.sleep(MOCK_CHUNK_DELAY)

    async def _stream_via_api(
        self,
        messages: list[dict],
        model: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        resolved_temperature = (
            temperature
            if temperature is not None
            else (self._temperature if self._temperature is not None else 0.7)
        )
        payload = {
            "model": model or self.settings.llm_model,
            "messages": messages,
            "stream": True,
            "temperature": resolved_temperature,
        }
        resolved_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
        if resolved_max_tokens is not None:
            payload["max_tokens"] = resolved_max_tokens
        headers = {"Authorization": f"Bearer {self.api_key}"}
        model_name = model or self.settings.llm_model
        LLM_CALLS.labels(provider=self.settings.llm_provider, model=model_name).inc()
        tokens = 0
        attempts = max(1, self.settings.llm_max_retries + 1)
        started = False

        def _record_failure() -> None:
            # 日志不记录 Key
            logger.exception(
                "llm_api_error",
                url=url,
                model=model_name,
                attempts=attempts,
            )
            LLM_FAILURES.labels(
                provider=self.settings.llm_provider, model=model_name
            ).inc()

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=60, transport=self._transport
                ) as client, client.stream(
                    "POST", url, json=payload, headers=headers
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            delta = json.loads(data)["choices"][0]["delta"].get(
                                "content", ""
                            )
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
                        if delta:
                            started = True
                            tokens += len(delta) // 4 + 1
                            yield delta
                break
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retryable = status in (408, 429) or status >= 500
                if not retryable or started or attempt == attempts - 1:
                    _record_failure()
                    raise
                await asyncio.sleep(
                    self.settings.llm_retry_base_delay * (2**attempt)
                )
            except httpx.TransportError:  # 连接/超时类错误
                if started or attempt == attempts - 1:
                    _record_failure()
                    raise
                await asyncio.sleep(
                    self.settings.llm_retry_base_delay * (2**attempt)
                )

        self.last_usage = {
            "prompt_tokens": sum(
                len(str(m.get("content") or "")) // 4 + 1 for m in messages
            ),
            "completion_tokens": tokens,
        }
        LLM_TOKENS.labels(kind="completion").inc(tokens)
        # 成本估算（近似单价，元/token；可按模型单价表细化，08 §9）
        LLM_COST.labels(currency="CNY").inc(tokens * 0.000001)
