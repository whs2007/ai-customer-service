"""会话记录接口（10 / 08 §4.4）：列表筛选、详情（引用/链路/工单/标注）、人工标注。"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import PageData, ResponseModel, ok
from app.models.session_annotation import SessionAnnotation
from app.models.ticket import Ticket
from app.models.trace_log import TraceLog
from app.models.user import Role, User
from app.schemas.chat import (
    AnnotationCreate,
    AnnotationOut,
    CitationOut,
    MessageOut,
    SessionDetailOut,
    SessionListItemOut,
    SessionOut,
    TicketBriefOut,
    TraceOut,
    TraceStepOut,
)
from app.services import annotation_service, chunk_service, session_service

router = APIRouter(tags=["sessions"])


def _parse_date(value: date, end_of_day: bool = False) -> datetime:
    """日期 → 当日零点/末日（Asia/Shanghai → UTC）。"""
    local = datetime.combine(
        value, time.max if end_of_day else time.min, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    return local.astimezone(timezone.utc)


@router.get("/sessions", response_model=ResponseModel[PageData[SessionListItemOut]])
async def list_sessions(
    start_date: date | None = Query(default=None, description="开始日期"),
    end_date: date | None = Query(default=None, description="结束日期"),
    intent: str | None = Query(default=None, max_length=50, description="意图"),
    status: str | None = Query(default=None, description="active/closed/transferred"),
    transferred: bool | None = Query(default=None, description="是否转人工"),
    keyword: str | None = Query(default=None, max_length=100, description="会话 ID/消息内容"),
    annotated: bool | None = Query(default=None, description="标注状态"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await session_service.list_sessions(
        db,
        page=page,
        page_size=page_size,
        start_date=_parse_date(start_date) if start_date else None,
        end_date=_parse_date(end_date, end_of_day=True) if end_date else None,
        intent=intent,
        status=status,
        transferred=transferred,
        keyword=keyword,
        annotated=annotated,
    )
    return ok(
        data=PageData[SessionListItemOut](
            items=[SessionListItemOut(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/sessions/{session_id}", response_model=ResponseModel[SessionDetailOut])
async def get_session(
    session_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """会话详情：消息（含引用明细）+ 链路 trace + 关联工单 + 标注。"""
    session, messages = await session_service.get_session_with_messages(db, session_id)
    cited_ids = [uuid.UUID(x) for m in messages for x in (m.cited_chunk_ids or [])]
    citation_map = await chunk_service.get_citations_by_chunk_ids(db, cited_ids)
    message_outs: list[MessageOut] = []
    for m in messages:
        out = MessageOut.model_validate(m)
        if m.role == "assistant":
            out.citations = [
                CitationOut(**citation_map[parsed])
                for cid_raw in (m.cited_chunk_ids or [])
                if (parsed := uuid.UUID(str(cid_raw))) in citation_map
            ]
        message_outs.append(out)

    trace_log = (
        await db.execute(
            select(TraceLog)
            .where(TraceLog.session_id == session_id)
            .order_by(TraceLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    ticket = (
        await db.execute(
            select(Ticket)
            .where(Ticket.session_id == session_id)
            .order_by(Ticket.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    annotation = await db.scalar(
        select(SessionAnnotation).where(SessionAnnotation.session_id == session_id)
    )

    return ok(
        data=SessionDetailOut(
            session=SessionOut.model_validate(session),
            messages=message_outs,
            trace=(
                TraceOut(
                    request_id=trace_log.request_id,
                    steps=[TraceStepOut(**s) for s in trace_log.steps],
                    latency_ms=trace_log.latency_ms,
                    created_at=trace_log.created_at,
                )
                if trace_log
                else None
            ),
            ticket=(
                TicketBriefOut(
                    id=ticket.id,
                    ticket_no=ticket.ticket_no,
                    status=ticket.status,
                    priority=ticket.priority,
                    created_at=ticket.created_at,
                )
                if ticket
                else None
            ),
            annotation=AnnotationOut.model_validate(annotation) if annotation else None,
        )
    )


@router.post(
    "/sessions/{session_id}/annotations",
    response_model=ResponseModel[AnnotationOut],
)
async def annotate_session(
    session_id: uuid.UUID,
    payload: AnnotationCreate,
    user: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    annotation = await annotation_service.upsert_annotation(db, session_id, payload, user)
    return ok(data=AnnotationOut.model_validate(annotation), message="标注已保存")

