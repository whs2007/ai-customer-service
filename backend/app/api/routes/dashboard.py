"""工作台统计接口（02 §7 / 08 §4.6）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import ResponseModel, ok
from app.models.user import Role, User
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=ResponseModel)
async def stats(
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await dashboard_service.get_stats(db))


@router.get("/trend", response_model=ResponseModel)
async def trend(
    days: int = Query(default=7, ge=1, le=30),
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await dashboard_service.get_trend(db, days))


@router.get("/intents", response_model=ResponseModel)
async def intents(
    days: int = Query(default=7, ge=1, le=30),
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await dashboard_service.get_intents(db, days))

