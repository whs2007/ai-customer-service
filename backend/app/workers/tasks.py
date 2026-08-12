"""Celery 任务定义：文档解析与向量化（08 §4.2 / §3.4）。

使用方式（需 Redis）：
    celery -A app.workers.tasks:celery_app worker -l info -P solo
配合 TASK_BACKEND=celery 使用；无 Redis 环境请保持 TASK_BACKEND=inline。
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_customer_service",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
)


@celery_app.task(name="documents.process", bind=True, max_retries=1)
def document_process_task(self, doc_id: str) -> dict[str, str]:
    """Celery 任务：解析 + 向量化（内部 asyncio.run 复用 importer 管线）。"""
    import asyncio

    from app.pipeline.importer import process_document

    try:
        doc = asyncio.run(process_document(doc_id))
        return {"doc_id": doc_id, "status": doc.status if doc else "missing"}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=5)

