"""系统管理接口（B6a）：日志审计 / 全量重建向量 / 知识库导出（仅 admin）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.services import admin_service

router = APIRouter(tags=["admin"])


@router.get("/audit-logs", response_model=ResponseModel[PageData[dict]])
async def list_audit_logs(
    action: str | None = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await admin_service.list_audit_logs(db, action, page, page_size)
    data = [
        {
            "id": str(log.id),
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "ip": log.ip,
            "created_at": log.created_at,
        }
        for log in items
    ]
    return ok(data=PageData[dict](items=data, total=total, page=page, page_size=page_size))


@router.post("/admin/rebuild-vectors", response_model=ResponseModel)
async def rebuild_vectors(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    result = await admin_service.rebuild_vectors(db)
    return ok(data=result, message="向量重建完成")


@router.get("/admin/export")
async def export_knowledge_bases(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    payload = await admin_service.export_knowledge_bases(db)
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return StreamingResponse(
        iter([body]),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=knowledge_bases_export.json"
        },
    )

