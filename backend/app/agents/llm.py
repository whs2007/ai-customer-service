"""LLM 客户端（08 §2：智谱 GLM 起步）。

配置 LLM_API_KEY 时调用 OpenAI 兼容 chat/completions（流式）；未配置时
使用模板化 mock 生成，保证离线可演示。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import structlog

from app.core.config import Settings, get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

MOCK_CHUNK_SIZE = 6
MOCK_CHUNK_DELAY = 0.02


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return bool(self.settings.llm_api_key)

    async def stream_chat(
        self, messages: list[dict], model: str = "", temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """按 token/chunk 流式返回生成文本。"""
        if self.available:
            async for chunk in self._stream_via_api(messages, model, temperature):
                yield chunk
        else:
            # mock：整段文本按小块输出（无真实 LLM 时保持流式体验）
            text = messages[-1].get("content", "")
            for i in range(0, len(text), MOCK_CHUNK_SIZE):
                yield text[i : i + MOCK_CHUNK_SIZE]
                await asyncio.sleep(MOCK_CHUNK_DELAY)

    async def _stream_via_api(
        self, messages: list[dict], model: str, temperature: float
    ) -> AsyncIterator[str]:
        base_url = (self.settings.llm_base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        url = f"{base_url}/chat/completions"
        payload = {
            "model": model or self.settings.llm_model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
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
                            delta = json.loads(data)["choices"][0]["delta"].get("content", "")
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
                        if delta:
                            yield delta
        except Exception as exc:  # noqa: BLE001
            # 日志不记录 Key
            logger.exception("llm_api_error", url=url, model=model or self.settings.llm_model)
            raise

