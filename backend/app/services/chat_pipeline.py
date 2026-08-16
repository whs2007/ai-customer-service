"""对话流水线（08 §4.4 / 开发文档 01 §3.1）：管理端与用户端共用。

管理端：kb_ids 由前端指定；用户端：kb_ids 由渠道配置解析（忽略前端传入），
引用脱敏（仅 document_name/question）。事件先落库后发布（开发文档 01 §9.5）。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.agents.graph import chat_graph
from app.agents.safety import check_prompt_injection
from app.agents.state import ChatState
from app.core.moderation import check_text
from app.models.session import ChatSession, SessionStatus
from app.models.user import User
from app.rag.retriever import filter_accessible_kb_ids
from app.services import model_profile_service, session_service
from app.services.event_service import publish_event

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def _resolve_kb_ids(
    db, kb_ids: list[uuid.UUID] | None, user: User, channel: str
) -> list[uuid.UUID] | None:
    """解析可用知识库：admin 模式过滤请求库；用户端模式按渠道配置。"""
    if kb_ids is not None:
        return await filter_accessible_kb_ids(db, kb_ids, user)
    from app.models.channel_config import ChannelConfig

    config = await db.get(ChannelConfig, channel)
    if config is None or not (config.default_kb_ids or []):
        return None
    requested = [uuid.UUID(str(x)) for x in config.default_kb_ids]
    return await filter_accessible_kb_ids(db, requested, user)


def _emit(queue: asyncio.Queue, event: str, data: dict) -> None:
    queue.put_nowait({"event": event, "data": data})


async def run_chat_pipeline(
    *,
    session_id: uuid.UUID | None,
    message: str,
    user: User,
    queue: asyncio.Queue,
    kb_ids: list[uuid.UUID] | None = None,
    model_profile_id: uuid.UUID | None = None,
    form_data: dict | None = None,
    sanitize_citations: bool = False,
    channel: str = "web",
) -> None:
    """对话主流程：会话准备（短连接）→ 图执行（不持有连接）→ 结果落库（短连接）。"""
    from app.db.session import get_session_factory

    request_id = str(uuid.uuid4())
    created_session_id: str | None = None
    state: ChatState | None = None
    user_message_id: uuid.UUID | None = None
    try:
        # ---- 阶段 1：会话准备（短连接）----
        async with get_session_factory()() as db:
            accessible = await _resolve_kb_ids(db, kb_ids, user, channel)
            if accessible is None:
                _emit(queue, "error", {"code": "40000", "message": "渠道未配置默认知识库，请联系管理员"})
                return
            if not accessible:
                _emit(queue, "error", {"code": "40000", "message": "所选知识库无效或无权限"})
                return

            if session_id is not None:
                session = await db.get(ChatSession, session_id)
                if session is None:
                    _emit(queue, "error", {"code": "40400", "message": "会话不存在"})
                    return
                # 用户端行级权限：仅本人会话（开发文档 01 §3.1）
                if session.user_id != user.id:
                    _emit(queue, "error", {"code": "40300", "message": "无权访问该会话"})
                    return
            else:
                session = None
                if channel == "web_user":
                    # 用户端同时最多 1 个 active 会话（12 §3.2）：复用最近 active
                    session = await db.scalar(
                        select(ChatSession)
                        .where(
                            ChatSession.user_id == user.id,
                            ChatSession.status == SessionStatus.ACTIVE.value,
                        )
                        .order_by(ChatSession.updated_at.desc())
                        .limit(1)
                    )
                if session is None:
                    session = ChatSession(user_id=user.id, kb_ids=[str(x) for x in accessible], channel=channel)
                    db.add(session)
                    await db.commit()
                    await db.refresh(session)

            created_session_id = str(session.id)
            _emit(queue, "message_start", {"session_id": created_session_id})

            user_message = await session_service.append_message(
                db, session.id, "user", message
            )
            user_message_id = user_message.id

            # Prompt 注入前置过滤（08 §8）：用户端公开入口更需严格
            injection = check_prompt_injection(message)
            if injection:
                guard = (
                    "抱歉，我检测到您的消息中包含疑似越权指令，"
                    "我只能回答与售后服务相关的问题。"
                )
                await session_service.append_message(
                    db, session.id, "assistant", guard, intent="other"
                )
                _emit(queue, "token", {"content": guard})
                _emit(
                    queue,
                    "done",
                    {
                        "message_id": None,
                        "intent": "other",
                        "ticket_no": None,
                        "session_id": created_session_id,
                    },
                )
                logger.warning(
                    "prompt_injection_blocked",
                    session_id=created_session_id,
                    user_id=str(user.id),
                    matched=injection,
                )
                return

            if session.status == SessionStatus.TRANSFERRED.value:
                logger.info(
                    "transferred_session_message_recorded",
                    session_id=created_session_id,
                )
                # 【修复 H2】转人工后留言仍发布 message.new，客服端实时可见（12 §3.3 / 13 §4）
                from app.models.ticket import Ticket

                ticket_row = await db.scalar(
                    select(Ticket)
                    .where(Ticket.session_id == session.id)
                    .order_by(Ticket.created_at.desc())
                    .limit(1)
                )
                if user_message_id is not None:
                    publish_event(
                        "message.new",
                        {
                            "session_id": created_session_id,
                            "user_id": str(user.id),
                            "ticket_status": ticket_row.status if ticket_row else None,
                            "assignee_id": (
                                str(ticket_row.assignee_id) if ticket_row and ticket_row.assignee_id else None
                            ),
                            "message_id": str(user_message_id),
                            "role": "user",
                            "created_at": user_message.created_at.isoformat(),
                            "from_user": str(user.id),
                        },
                    )
                _emit(
                    queue,
                    "done",
                    {
                        "message_id": None,
                        "intent": "transfer",
                        "ticket_no": None,
                        "session_id": created_session_id,
                    },
                )
                return

            recent = await session_service.get_recent_messages(db, session.id)
            messages = [{"role": m.role, "content": m.content} for m in recent]
            if form_data:
                form_text = "；".join(f"{k}={v}" for k, v in form_data.items() if v)
                if messages:
                    messages[-1] = {
                        **messages[-1],
                        "content": messages[-1]["content"] + f"\n[表单已提交：{form_text}]",
                    }

            profile = None
            if model_profile_id is not None:
                profile = await model_profile_service.get_profile(db, model_profile_id)
            else:
                profile = await model_profile_service.get_default_profile(db)

            state = {
                "session_id": created_session_id,
                "user_id": str(user.id),
                "messages": messages,
                "kb_ids": [str(x) for x in accessible],
                "escalation_count": session.escalation_count,
                "form_data": form_data,
                "model_profile_id": (
                    str(model_profile_id) if model_profile_id is not None else None
                ),
                "queue": queue,
                "trace": [],
                "citations": [],
                "answer": "",
            }
            if profile:
                state["model_name"] = profile.model

        # ---- 阶段 2：图执行（不持有连接，LLM 流式期间连接池空闲）----
        assert state is not None
        started = time.perf_counter()
        result = await chat_graph.ainvoke(state)
        latency_ms = int((time.perf_counter() - started) * 1000)

        # ---- 阶段 3：结果落库（短连接）----
        assert created_session_id is not None
        async with get_session_factory()() as db:
            answer = (result.get("answer") or "").strip()
            if answer:
                moderation = await check_text(db, answer)
                if moderation["blocked"]:
                    answer = "抱歉，该内容暂无法回答。"
            assistant = None
            if answer:
                assistant = await session_service.append_message(
                    db,
                    uuid.UUID(created_session_id),
                    "assistant",
                    answer,
                    intent=result.get("intent"),
                    cited_chunk_ids=[
                        str(c["chunk_id"]) for c in result.get("citations", [])
                    ],
                )

            ticket_no = None
            ticket_row = None
            if result.get("ticket"):
                ticket_no = result["ticket"]["ticket_no"]
                await session_service.append_message(
                    db,
                    uuid.UUID(created_session_id),
                    "system",
                    f"已为您转接人工客服，工单号 {ticket_no}，请稍候",
                    intent=result.get("intent"),
                )
                from app.models.ticket import Ticket

                ticket_row = await db.scalar(
                    select(Ticket).where(Ticket.ticket_no == ticket_no)
                )

            session_row = await db.get(ChatSession, uuid.UUID(created_session_id))
            if session_row is not None:
                if result.get("ticket"):
                    session_row.status = "transferred"
                session_row.escalation_count = result.get(
                    "escalation_count", session_row.escalation_count
                )
                await db.commit()

            await session_service.save_trace(
                db,
                uuid.UUID(created_session_id),
                request_id=request_id,
                steps=result.get("trace", []),
                latency_ms=latency_ms,
                message_id=assistant.id if assistant else None,
                tokens=result.get("token_usage"),
            )

            # ---- 事件发布（先落库后发布，11 §9；须在 done 之前完成，
            # 避免路由消费 done 后取消任务导致事件丢失）----
            ticket_status = ticket_row.status if ticket_row else None
            assignee_id = str(ticket_row.assignee_id) if ticket_row and ticket_row.assignee_id else None
            common = {
                "session_id": created_session_id,
                "user_id": str(user.id),
                "ticket_status": ticket_status,
                "assignee_id": assignee_id,
            }
            if user_message_id is not None:
                publish_event(
                    "message.new",
                    {
                        **common,
                        "message_id": str(user_message_id),
                        "role": "user",
                        "created_at": user_message.created_at.isoformat(),
                        "from_user": str(user.id),
                    },
                )
            if assistant is not None:
                publish_event(
                    "message.new",
                    {
                        **common,
                        "message_id": str(assistant.id),
                        "role": "assistant",
                        "created_at": assistant.created_at.isoformat(),
                        "from_agent": None,
                    },
                )
            if ticket_row is not None:
                publish_event(
                    "ticket.created",
                    {
                        **common,
                        "ticket_id": str(ticket_row.id),
                        "ticket_no": ticket_no,
                        "priority": ticket_row.priority,
                    },
                )

            # 精简字段 + UUID 转字符串后下发
            citations = _format_citations(result, sanitize=sanitize_citations)
            _emit(queue, "citations", {"citations": citations})
            _emit(
                queue,
                "done",
                {
                    "message_id": str(assistant.id) if assistant else None,
                    "intent": result.get("intent"),
                    "ticket_no": ticket_no,
                    "session_id": created_session_id,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat_pipeline_error", request_id=request_id)
        # 【修复 M7】仅业务异常（AppError）透出内部语义，其余统一友好文案，避免内部信息外泄
        from app.core.exceptions import AppError

        if isinstance(exc, AppError):
            code = exc.code
            message = exc.message
        else:
            code = 50000
            message = "服务内部错误，请稍后重试"
        _emit(queue, "error", {"code": str(code), "message": message})


def _format_citations(result: dict, sanitize: bool) -> list[dict]:
    """引用字段精简；用户端只暴露 document_name/question（11 §10 字段最小化）。"""
    _CITATION_FIELDS = (
        "chunk_id",
        "kb_id",
        "document_name",
        "page",
        "row",
        "question",
        "answer",
        "retrieval_score",
        "rerank_score",
    )
    items: list[dict[str, Any]] = []
    for c in result.get("citations", []):
        if sanitize:
            items.append(
                {
                    "document_name": c.get("document_name"),
                    "question": c.get("question"),
                }
            )
            continue
        items.append(
            {
                field: str(c[field]) if field in ("chunk_id", "kb_id") else c.get(field)
                for field in _CITATION_FIELDS
            }
        )
    return items
