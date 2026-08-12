"""健康检查：/health（无需登录）。"""

from __future__ import annotations

from sqlalchemy import text

from app.api.deps import get_db
from app.core.alerts import check_alerts
from app.core.config import get_settings
from app.core.metrics import QUEUE_LAG, render_metrics
from app.core.response import ResponseModel, ok
from app.core.redis import ping_redis
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.models.user import Role, User

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ResponseModel)
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """返回应用、数据库、Redis 组件状态（Redis 不可用不视为应用故障）。"""
    settings = get_settings()

    database = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database = "error"

    redis = "skipped" if settings.skip_redis else ("ok" if await ping_redis() else "unavailable")

    components = {
        "database": database,
        "redis": redis,
    }
    status = "ok" if database == "ok" else "degraded"
    return ok(
        data={
            "status": status,
            "app": settings.app_name,
            "version": settings.version,
            "components": components,
        }
    )


@router.get("/metrics")
async def metrics(
    _: User = Depends(require_roles(Role.ADMIN)),
) -> PlainTextResponse:
    """Prometheus 指标（08 §9，仅 admin，Prometheus 抓取需配置 Bearer token）；
    同时执行日志告警检查（占位）。"""
    from app.core.redis import get_redis_client

    # 队列积压：celery 模式读 Redis 默认队列长度；inline 模式为 0
    redis_client = get_redis_client()
    lag = 0
    if redis_client is not None:
        try:
            lag = await redis_client.llen("celery")
        except Exception:  # noqa: BLE001
            lag = 0
    QUEUE_LAG.set(lag)
    check_alerts()
    body, content_type = render_metrics()
    return PlainTextResponse(body, media_type=content_type)
