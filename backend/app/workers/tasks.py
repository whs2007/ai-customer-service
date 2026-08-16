"""Celery 任务定义：文档解析与向量化、评测执行、日志清理（08 §4.2 / §3.4）。

使用方式（需 Redis）：
    celery -A app.workers.tasks:celery_app worker -l info -P solo
配合 TASK_BACKEND=celery 使用；无 Redis 环境请保持 TASK_BACKEND=inline。
"""

from __future__ import annotations

from datetime import UTC

from celery import Celery
from celery.schedules import crontab

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
    # 任务可靠性（08 §3.4 / B6b）：worker 崩溃不丢任务、超时熔断、定期回收
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=900,
    task_soft_time_limit=840,
    worker_max_tasks_per_child=200,
    broker_transport_options={"visibility_timeout": 3600},
    # 每日定时维护（beat 服务执行，见 docker-compose）
    beat_schedule={
        "prune-trace-logs-daily": {
            "task": "maintenance.prune_trace_logs",
            "schedule": crontab(hour=3, minute=30),
        },
    },
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
        raise self.retry(exc=exc, countdown=5) from exc


@celery_app.task(name="evaluations.run", bind=True, max_retries=1)
def eval_task_run(self, task_id: str) -> dict[str, str]:
    """Celery 任务：评测任务逐条执行（内部 asyncio.run 复用 eval_service）。"""
    import asyncio

    from app.services.eval_service import run_eval_task

    try:
        asyncio.run(run_eval_task(task_id))
        return {"task_id": task_id, "status": "done"}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=5) from exc


async def prune_expired_trace_logs() -> int:
    """按 log_retention_days 清理过期链路日志（trace_logs），返回删除条数。"""
    from datetime import datetime, timedelta
    from typing import cast

    from sqlalchemy import delete
    from sqlalchemy.engine import CursorResult

    from app.core.config import get_settings
    from app.db.session import get_session_factory
    from app.models.trace_log import TraceLog

    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.log_retention_days)
    async with get_session_factory()() as db:
        result = cast(
            CursorResult,
            await db.execute(
                delete(TraceLog).where(TraceLog.created_at < cutoff)
            ),
        )
        await db.commit()
        return result.rowcount or 0


@celery_app.task(name="maintenance.prune_trace_logs")
def prune_trace_logs() -> dict[str, int]:
    """Celery 包装：每日清理过期链路日志（beat 调度）。"""
    import asyncio

    removed = asyncio.run(prune_expired_trace_logs())
    return {"removed": removed}
