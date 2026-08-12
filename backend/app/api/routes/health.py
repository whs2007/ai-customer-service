"""健康检查：/health（无需登录）。"""

from __future__ import annotations

from sqlalchemy import text

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.response import ResponseModel, ok
from app.core.redis import ping_redis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
