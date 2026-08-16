"""健康检查：/health（无需登录）。"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.alerts import check_alerts
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.metrics import QUEUE_LAG, render_metrics
from app.core.redis import ping_redis
from app.core.response import ResponseModel, ok
from app.models.user import Role

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


async def _metrics_access(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """/metrics 访问控制：配置了 METRICS_TOKEN 时优先用静态抓取 token；
    未配置则回退 admin JWT（含会话版本校验）。"""
    settings = get_settings()
    if not settings.metrics_enabled:
        raise NotFoundError("指标未启用")
    auth = request.headers.get("Authorization", "")
    if settings.metrics_token and hmac.compare_digest(
        auth, f"Bearer {settings.metrics_token}"
    ):
        return
    user = await get_current_user(request, db)
    if user.role != Role.ADMIN.value:
        raise ForbiddenError("无权限执行此操作")


@router.get("/metrics")
async def metrics(
    _: None = Depends(_metrics_access),
) -> PlainTextResponse:
    """Prometheus 指标（08 §9：METRICS_TOKEN 或 admin JWT 二选一）；
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
