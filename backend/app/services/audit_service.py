"""审计日志公共方法（08 §4.8）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mask import mask_object
from app.models.audit_log import AuditLog


async def write_audit(
    db: AsyncSession,
    action: str,
    user_id: str | None = None,
    ip: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=mask_object(detail) if detail else detail,
            ip=ip,
        )
    )
