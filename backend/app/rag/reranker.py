"""重排客户端（08 §4.3 / §11 #15：SiliconFlow BAAI/bge-reranker-v2-m3）。

密钥（RERANK_API_KEY）仅从 .env 读取，不写入代码/文档/日志。
"""

from __future__ import annotations

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.exceptions import UpstreamError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class RerankClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def available(self) -> bool:
        """未配置 Key/模型时不可用（调用方降级为混合检索）。"""
        return bool(self.settings.rerank_api_key and self.settings.rerank_model)

    @property
    def model_name(self) -> str:
        return self.settings.rerank_model or ""

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[float]:
        """调用 SiliconFlow /rerank，返回与 documents 顺序一致的分数列表。"""
        base_url = (self.settings.rerank_base_url or "https://api.siliconflow.cn/v1").rstrip("/")
        url = f"{base_url}/rerank"
        payload: dict = {
            "model": self.settings.rerank_model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        headers = {"Authorization": f"Bearer {self.settings.rerank_api_key}"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            # 日志中只记录模型与 URL，绝不记录 API Key
            logger.exception(
                "rerank_api_error",
                url=url,
                model=self.settings.rerank_model,
                documents=len(documents),
            )
            raise UpstreamError("重排服务暂不可用，请稍后重试") from exc

        results = data.get("results") or data.get("data") or []
        indexed = {
            int(item.get("index", i)): float(
                item.get("relevance_score", item.get("score", 0.0))
            )
            for i, item in enumerate(results)
        }
        return [indexed.get(i, 0.0) for i in range(len(documents))]
