"""工作台统计服务（02 §7 口径）。

无 Redis/Celery：按需计算 + 进程内 30s 缓存，并将当日结果落 dashboard_stats
（为后续 Celery 定时聚合铺路，08 §4.6）。
"""

from __future__ import annotations

import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_stat import DashboardStat
from app.models.message import Message
from app.models.session import ChatSession
from app.models.ticket import Ticket

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, object]] = {}


def _day_bounds(offset_days: int = 0) -> tuple[datetime, datetime]:
    day = (datetime.now(LOCAL_TZ).date() - timedelta(days=offset_days))
    start = datetime.combine(day, dtime.min, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    end = datetime.combine(day, dtime.max, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    return start, end


def _cached(key: str):
    """进程内缓存：TTL 30s（无 Redis 时的按需聚合兜底）。"""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _set_cache(key: str, value: object) -> None:
    _cache[key] = (time.monotonic(), value)


async def compute_today_stats(db: AsyncSession) -> dict:
    """02 §7 口径：今日会话数 / AI 自动解决率 / 转人工数量 / 知识库命中率。

    AI 自动解决率口径说明：02 §7 的"AI 独立完结会话数"在无"关闭"事件机制下，
    以"当日创建且未转人工的会话数"近似（转人工即视为 AI 未能独立完结）。
    """
    start, end = _day_bounds()
    sessions_count = (
        await db.scalar(
            select(func.count()).select_from(ChatSession).where(
                ChatSession.created_at >= start, ChatSession.created_at <= end
            )
        )
        or 0
    )
    solved_count = (
        await db.scalar(
            select(func.count()).select_from(ChatSession).where(
                ChatSession.created_at >= start,
                ChatSession.created_at <= end,
                ChatSession.status != "transferred",
            )
        )
        or 0
    )
    transfer_count = (
        await db.scalar(
            select(func.count()).select_from(Ticket).where(
                Ticket.created_at >= start, Ticket.created_at <= end
            )
        )
        or 0
    )
    assistant_total = (
        await db.scalar(
            select(func.count()).select_from(Message).where(
                Message.created_at >= start,
                Message.created_at <= end,
                Message.role == "assistant",
            )
        )
        or 0
    )
    kb_hit_total = (
        await db.scalar(
            select(func.count()).select_from(Message).where(
                Message.created_at >= start,
                Message.created_at <= end,
                Message.role == "assistant",
                func.jsonb_array_length(Message.cited_chunk_ids) > 0,
            )
        )
        or 0
    )
    intent_rows = (
        await db.execute(
            select(Message.intent, func.count(Message.id))
            .where(
                Message.created_at >= start,
                Message.created_at <= end,
                Message.role == "assistant",
                Message.intent.is_not(None),
            )
            .group_by(Message.intent)
        )
    ).all()
    intent_distribution = {intent: count for intent, count in intent_rows}

    ai_solved_rate = round(solved_count / sessions_count * 100, 2) if sessions_count else 0.0
    kb_hit_rate = round(kb_hit_total / assistant_total * 100, 2) if assistant_total else 0.0

    stat = {
        "stat_date": str(datetime.now(LOCAL_TZ).date()),
        "today_sessions": sessions_count,
        "ai_solved_count": solved_count,
        "ai_solved_rate": ai_solved_rate,
        "transfer_count": transfer_count,
        "kb_hit_rate": kb_hit_rate,
        "intent_distribution": intent_distribution,
    }
    # 落表：当日行 upsert（供后续定时聚合读取）
    row = await db.get(DashboardStat, datetime.now(LOCAL_TZ).date())
    if row is None:
        row = DashboardStat(stat_date=datetime.now(LOCAL_TZ).date())
        db.add(row)
    row.sessions_count = sessions_count
    row.ai_solved_count = solved_count
    row.ai_solved_rate = Decimal(str(ai_solved_rate))
    row.transfer_count = transfer_count
    row.kb_hit_rate = Decimal(str(kb_hit_rate))
    row.intent_distribution = intent_distribution
    await db.commit()
    return stat


async def get_stats(db: AsyncSession) -> dict:
    cached = _cached("stats")
    if cached is not None:
        return cached  # type: ignore[return-value]
    data = await compute_today_stats(db)
    _set_cache("stats", data)
    return data


async def get_trend(db: AsyncSession, days: int = 7) -> list[dict]:
    key = f"trend:{days}"
    cached = _cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    start, _ = _day_bounds(days - 1)
    rows = (
        await db.execute(
            select(
                func.date(func.timezone("Asia/Shanghai", ChatSession.created_at)).label("d"),
                func.count(ChatSession.id),
            )
            .where(ChatSession.created_at >= start)
            .group_by("d")
        )
    ).all()
    counts = {str(d): count for d, count in rows}
    today = datetime.now(LOCAL_TZ).date()
    data = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        data.append({"date": str(day), "sessions": counts.get(str(day), 0)})
    _set_cache(key, data)
    return data


async def get_intents(db: AsyncSession, days: int = 7) -> dict:
    key = f"intents:{days}"
    cached = _cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    start, _ = _day_bounds(days - 1)
    rows = (
        await db.execute(
            select(Message.intent, func.count(Message.id))
            .where(
                Message.created_at >= start,
                Message.role == "assistant",
                Message.intent.is_not(None),
            )
            .group_by(Message.intent)
        )
    ).all()
    items = [{"intent": intent, "count": count} for intent, count in rows]
    data = {"items": items, "total": sum(c for _, c in rows)}
    _set_cache(key, data)
    return data

