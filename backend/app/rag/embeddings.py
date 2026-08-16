"""Embedding 客户端（08 §4.2 / §11 #2）。

- 配置了 EMBEDDING_API_KEY：调用 OpenAI 兼容 /embeddings 接口；
- 未配置：使用确定性 mock 向量（sha256 种子 + 归一化），仅限本地开发跑通链路。
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from typing import Any

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.exceptions import UpstreamError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# 【修复 M9】API 向量短时缓存：同文本批在 TTL 内复用，降低调用成本与延迟
_EMBED_CACHE_MAX = 512
_EMBED_CACHE_TTL_SECONDS = 600
_embed_cache: dict[str, tuple[float, list[list[float]]]] = {}


class EmbeddingClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.settings.embedding_api_key:
            vectors = await self._embed_via_api_cached(texts)
        else:
            vectors = [self._mock_embed(text) for text in texts]
        return vectors

    async def _embed_via_api_cached(self, texts: list[str]) -> list[list[float]]:
        key = f"{self.settings.embedding_model}|{chr(31).join(texts)}"
        hit = _embed_cache.get(key)
        now = time.monotonic()
        if hit is not None and now - hit[0] < _EMBED_CACHE_TTL_SECONDS:
            return hit[1]
        vectors = await self._embed_via_api(texts)
        if len(_embed_cache) >= _EMBED_CACHE_MAX:
            # 超限清理最旧一半（近似 LRU，成本低）
            oldest = sorted(_embed_cache.items(), key=lambda kv: kv[1][0])
            for k, _ in oldest[: _EMBED_CACHE_MAX // 2]:
                _embed_cache.pop(k, None)
        _embed_cache[key] = (now, vectors)
        return vectors

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    async def _embed_via_api(self, texts: list[str]) -> list[list[float]]:
        base_url = (self.settings.embedding_base_url or "").rstrip("/")
        url = f"{base_url}/embeddings" if base_url else "https://api.zhipuai.com/embeddings"
        payload: dict[str, Any] = {"model": self.settings.embedding_model, "input": texts}
        # embedding-3 默认返回 2048 维，需显式指定维度以匹配 chunks.embedding 的 1024 维列
        if "embedding-3" in self.settings.embedding_model:
            payload["dimensions"] = self.settings.embedding_dim
        headers = {"Authorization": f"Bearer {self.settings.embedding_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()["data"]
                vectors = [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]
        except Exception as exc:  # noqa: BLE001
            logger.exception("embedding_api_error", url=url, model=self.settings.embedding_model)
            raise UpstreamError("向量化服务暂不可用") from exc

        dim = self.settings.embedding_dim
        for vec in vectors:
            if len(vec) != dim:
                raise UpstreamError(f"向量维度与配置不一致（期望 {dim}，实际 {len(vec)}）")
        return vectors

    def _mock_embed(self, text: str) -> list[float]:
        """确定性词法向量（开发用）：

        【变更】B2 版为随机哈希，无语义结构；现改为字符 n-gram（单字 + 相邻双字）
        哈希叠加，使共享子串的文本获得更高余弦相似度，支撑检索排序可解释。
        生产环境配置真实 EMBEDDING_API_KEY 后走正式模型。
        """
        dim = self.settings.embedding_dim
        chars = [c.lower() for c in text if not c.isspace()]
        grams = set(chars)
        grams.update(f"{a}{b}" for a, b in zip(chars, chars[1:], strict=False))

        vec = [0.0] * dim
        for gram in grams:
            seed = int.from_bytes(hashlib.sha256(gram.encode("utf-8")).digest()[:8], "big")
            rng = random.Random(seed)
            for _ in range(24):  # 每个 gram 贡献少量随机符号分量
                idx = rng.randrange(dim)
                vec[idx] += 1.0 if rng.random() < 0.5 else -1.0

        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
