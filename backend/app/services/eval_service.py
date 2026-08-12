"""应用评测服务（08 §4.9 / 09）：评测集、样本、任务执行、报告、回流候选。"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import chat_graph
from app.agents.state import ChatState
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.eval_candidate import EvalCandidate, EvalCandidateStatus
from app.models.eval_result import EvalResult
from app.models.eval_sample import EvalSample
from app.models.eval_set import EvalSet
from app.models.eval_task import EvalTask, EvalTaskStatus
from app.models.model_profile import ModelProfile
from app.models.user import User
from app.schemas.evaluation import (
    EvalSetCreate,
    EvalSetOut,
    EvalTaskCreate,
    SampleCreate,
)
from app.services import model_profile_service
from app.services.judge_service import PASS_THRESHOLD, judge_answer

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------- 评测集 ----------

async def list_eval_sets(db: AsyncSession) -> list[EvalSetOut]:
    stmt = (
        select(EvalSet, func.count(EvalSample.id).label("sample_count"))
        .outerjoin(EvalSample, EvalSample.eval_set_id == EvalSet.id)
        .group_by(EvalSet.id)
        .order_by(EvalSet.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        EvalSetOut(
            id=es.id, name=es.name, description=es.description, source=es.source,
            sample_count=count, created_at=es.created_at, updated_at=es.updated_at,
        )
        for es, count in rows
    ]


async def get_eval_set(db: AsyncSession, set_id: uuid.UUID) -> EvalSet:
    es = await db.get(EvalSet, set_id)
    if es is None:
        raise NotFoundError("评测集不存在")
    return es


async def create_eval_set(db: AsyncSession, payload: EvalSetCreate, user: User) -> EvalSet:
    existing = await db.scalar(select(EvalSet).where(EvalSet.name == payload.name.strip()))
    if existing is not None:
        raise ConflictError("该名称已存在")
    es = EvalSet(
        name=payload.name.strip(),
        description=payload.description.strip(),
        created_by=user.id,
    )
    db.add(es)
    await db.commit()
    await db.refresh(es)
    return es


async def update_eval_set(
    db: AsyncSession, set_id: uuid.UUID, payload: EvalSetCreate
) -> EvalSet:
    es = await get_eval_set(db, set_id)
    conflict = await db.scalar(
        select(EvalSet).where(EvalSet.name == payload.name.strip(), EvalSet.id != set_id)
    )
    if conflict is not None:
        raise ConflictError("该名称已存在")
    es.name = payload.name.strip()
    es.description = payload.description.strip()
    await db.commit()
    await db.refresh(es)
    return es


async def delete_eval_set(db: AsyncSession, set_id: uuid.UUID) -> None:
    await get_eval_set(db, set_id)
    # 样本/任务/结果通过外键级联删除
    await db.delete(await db.get(EvalSet, set_id))
    await db.commit()


# ---------- 样本 ----------

async def list_samples(
    db: AsyncSession, set_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[EvalSample], int]:
    total = (
        await db.scalar(
            select(func.count()).select_from(EvalSample).where(
                EvalSample.eval_set_id == set_id
            )
        )
        or 0
    )
    result = await db.execute(
        select(EvalSample)
        .where(EvalSample.eval_set_id == set_id)
        .order_by(EvalSample.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def add_sample(
    db: AsyncSession, set_id: uuid.UUID, payload: SampleCreate, source: str = "manual"
) -> EvalSample:
    await get_eval_set(db, set_id)
    sample = EvalSample(
        eval_set_id=set_id,
        question=payload.question.strip(),
        expected_answer=payload.expected_answer.strip(),
        expected_chunks=[str(c) for c in payload.expected_chunks],
        source=source,
    )
    db.add(sample)
    await db.commit()
    await db.refresh(sample)
    return sample


async def import_samples(
    db: AsyncSession, set_id: uuid.UUID, items: list[SampleCreate]
) -> int:
    await get_eval_set(db, set_id)
    for item in items:
        db.add(
            EvalSample(
                eval_set_id=set_id,
                question=item.question.strip(),
                expected_answer=item.expected_answer.strip(),
                expected_chunks=[str(c) for c in item.expected_chunks],
                source="manual",
            )
        )
    await db.commit()
    return len(items)


async def import_public_samples(db: AsyncSession, set_id: uuid.UUID) -> int:
    """一键导入内置 30 条公开样例（幂等：已导入则 409）。"""
    await get_eval_set(db, set_id)
    has_public = await db.scalar(
        select(EvalSample.id)
        .where(EvalSample.eval_set_id == set_id, EvalSample.source == "public")
        .limit(1)
    )
    if has_public:
        raise ConflictError("该评测集已导入过公开样例")
    from app.services.eval_seed import EVAL_PUBLIC_SAMPLES

    for item in EVAL_PUBLIC_SAMPLES:
        db.add(
            EvalSample(
                eval_set_id=set_id,
                question=item["question"],
                expected_answer=item["expected_answer"],
                expected_chunks=[],
                source="public",
            )
        )
    await db.commit()
    return len(EVAL_PUBLIC_SAMPLES)


# ---------- 任务 ----------

async def create_eval_task(
    db: AsyncSession, payload: EvalTaskCreate, user: User
) -> EvalTask:
    await get_eval_set(db, payload.eval_set_id)
    total = (
        await db.scalar(
            select(func.count()).select_from(EvalSample).where(
                EvalSample.eval_set_id == payload.eval_set_id
            )
        )
        or 0
    )
    if total == 0:
        raise BadRequestError("评测集暂无样本，请先导入样本")
    task = EvalTask(
        eval_set_id=payload.eval_set_id,
        model_profile_id=payload.model_profile_id,
        kb_ids=[str(x) for x in payload.kb_ids],
        status=EvalTaskStatus.PENDING.value,
        total=total,
        created_by=user.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def process_eval_task_job(task_id: str) -> None:
    """任务派发：inline 进程内执行 / celery 入队（TASK_BACKEND）。"""
    if get_settings().task_backend == "celery":
        from app.workers.tasks import eval_task_run

        eval_task_run.delay(task_id)
    else:
        await run_eval_task(task_id)


async def run_eval_task(task_id: str) -> None:
    """逐条走对话链路生成回答 → LLM-as-judge 打分 → 进度与报告落库。"""
    from app.db.session import get_session_factory

    async with get_session_factory()() as db:
        task = await db.get(EvalTask, uuid.UUID(task_id))
        if task is None:
            return
        task.status = EvalTaskStatus.RUNNING.value
        task.error_message = None
        task.progress = 0
        await db.commit()
        try:
            samples = (
                await db.execute(
                    select(EvalSample)
                    .where(EvalSample.eval_set_id == task.eval_set_id)
                    .order_by(EvalSample.created_at)
                )
            ).scalars().all()
            profile = None
            if task.model_profile_id:
                profile = await model_profile_service.get_profile(
                    db, task.model_profile_id
                )
            else:
                profile = await model_profile_service.get_default_profile(db)
            kb_ids = [str(x) for x in task.kb_ids]
            total = len(samples)
            avg_sum = 0.0
            passed_count = 0
            for index, sample in enumerate(samples, start=1):
                state: ChatState = {
                    "session_id": str(uuid.uuid4()),
                    "messages": [{"role": "user", "content": sample.question}],
                    "kb_ids": kb_ids,
                    "escalation_count": 0,
                    "citations": [],
                    "answer": "",
                    "trace": [],
                    "queue": None,
                    "eval_mode": True,
                }
                if profile:
                    state["model_name"] = profile.model
                result = await chat_graph.ainvoke(state)
                answer = result.get("answer", "")
                citations = [
                    {
                        field: (
                            str(c[field])
                            if field in ("chunk_id", "kb_id")
                            else c.get(field)
                        )
                        for field in (
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
                    }
                    for c in result.get("citations", [])
                ]
                scores = await judge_answer(
                    sample.question,
                    sample.expected_answer,
                    answer,
                    model_name=profile.model if profile else "",
                )
                accuracy = scores.get("accuracy") or 0.0
                passed = accuracy >= PASS_THRESHOLD
                db.add(
                    EvalResult(
                        task_id=task.id,
                        sample_id=sample.id,
                        answer=answer,
                        citations=citations,
                        scores=scores,
                        passed=passed,
                    )
                )
                avg_sum += accuracy
                passed_count += int(passed)
                task.progress = index
                await db.commit()

            avg = round(avg_sum / total, 2) if total else 0.0
            task.score_avg = avg
            task.metrics = {
                "accuracy": avg,
                "pass_rate": round(passed_count / total * 100, 2) if total else 0.0,
                "passed_count": passed_count,
            }
            task.status = EvalTaskStatus.COMPLETED.value
            await db.commit()
            logger.info(
                "eval_task_completed",
                task_id=str(task.id),
                total=total,
                score_avg=avg,
            )
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            task = await db.get(EvalTask, uuid.UUID(task_id))
            if task is not None:
                task.status = EvalTaskStatus.FAILED.value
                task.error_message = str(exc)[:500]
                await db.commit()
            logger.exception("eval_task_failed", task_id=task_id, error=str(exc)[:500])


async def list_eval_tasks(db: AsyncSession, page: int, page_size: int) -> tuple[list[dict], int]:
    total = await db.scalar(select(func.count()).select_from(EvalTask)) or 0
    stmt = (
        select(EvalTask, EvalSet.name, ModelProfile.name)
        .join(EvalSet, EvalSet.id == EvalTask.eval_set_id)
        .outerjoin(ModelProfile, ModelProfile.id == EvalTask.model_profile_id)
        .order_by(EvalTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()
    items = []
    for task, set_name, profile_name in rows:
        d = _task_to_dict(task, set_name, profile_name)
        items.append(d)
    return items, total


def _task_to_dict(
    task: EvalTask, set_name: str = "", profile_name: str = ""
) -> dict:
    return {
        "id": str(task.id),
        "eval_set_id": str(task.eval_set_id),
        "eval_set_name": set_name,
        "model_profile_id": str(task.model_profile_id) if task.model_profile_id else None,
        "model_name": profile_name or "",
        "kb_ids": task.kb_ids,
        "status": task.status,
        "progress": task.progress,
        "total": task.total,
        "score_avg": float(task.score_avg) if task.score_avg is not None else None,
        "metrics": task.metrics,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


async def get_eval_task(db: AsyncSession, task_id: uuid.UUID) -> dict:
    task = await db.get(EvalTask, task_id)
    if task is None:
        raise NotFoundError("评测任务不存在")
    set_name = await db.scalar(
        select(EvalSet.name).where(EvalSet.id == task.eval_set_id)
    )
    profile_name = None
    if task.model_profile_id:
        profile_name = await db.scalar(
            select(ModelProfile.name).where(ModelProfile.id == task.model_profile_id)
        )
    return _task_to_dict(task, set_name or "", profile_name or "")


async def rerun_eval_task(db: AsyncSession, task_id: uuid.UUID) -> EvalTask:
    task = await db.get(EvalTask, task_id)
    if task is None:
        raise NotFoundError("评测任务不存在")
    await db.execute(delete(EvalResult).where(EvalResult.task_id == task_id))
    task.status = EvalTaskStatus.PENDING.value
    task.progress = 0
    task.score_avg = None
    task.metrics = None
    task.error_message = None
    await db.commit()
    await db.refresh(task)
    return task


async def delete_eval_task(db: AsyncSession, task_id: uuid.UUID) -> None:
    task = await db.get(EvalTask, task_id)
    if task is None:
        raise NotFoundError("评测任务不存在")
    await db.delete(task)
    await db.commit()


async def get_report(db: AsyncSession, task_id: uuid.UUID) -> dict:
    task = await get_eval_task(db, task_id)
    rows = (
        await db.execute(
            select(EvalResult, EvalSample)
            .join(EvalSample, EvalSample.id == EvalResult.sample_id)
            .where(EvalResult.task_id == task_id)
            .order_by(EvalSample.created_at)
        )
    ).all()
    results = []
    passed_count = 0
    total = len(rows)
    for result, sample in rows:
        passed_count += int(result.passed)
        results.append(
            {
                "id": str(result.id),
                "sample_id": str(result.sample_id),
                "question": sample.question,
                "expected_answer": sample.expected_answer,
                "answer": result.answer,
                "citations": result.citations,
                "scores": result.scores,
                "passed": result.passed,
            }
        )
    metrics = task["metrics"] or {}
    return {
        "task": task,
        "score_avg": task["score_avg"],
        "pass_rate": float(metrics.get("pass_rate", 0.0)),
        "total": total,
        "passed_count": passed_count,
        "metrics": metrics,
        "results": results,
    }


async def update_result_passed(
    db: AsyncSession, result_id: uuid.UUID, passed: bool
) -> None:
    """人工调整通过状态 → 重算任务平均分与通过率（09 §7）。"""
    result = await db.get(EvalResult, result_id)
    if result is None:
        raise NotFoundError("评测明细不存在")
    result.passed = passed
    task = await db.get(EvalTask, result.task_id)
    if task is not None and task.status == EvalTaskStatus.COMPLETED.value:
        rows = (
            await db.execute(select(EvalResult).where(EvalResult.task_id == task.id))
        ).scalars().all()
        total = len(rows)
        if total:
            avg_sum = sum(float(r.scores.get("accuracy") or 0.0) for r in rows)
            passed_count = sum(1 for r in rows if r.passed)
            avg = round(avg_sum / total, 2)
            task.score_avg = avg
            task.metrics = {
                "accuracy": avg,
                "pass_rate": round(passed_count / total * 100, 2),
                "passed_count": passed_count,
            }
    await db.commit()


# ---------- 回流候选 ----------

async def list_candidates(db: AsyncSession) -> list[EvalCandidate]:
    result = await db.execute(
        select(EvalCandidate)
        .where(EvalCandidate.status == EvalCandidateStatus.PENDING.value)
        .order_by(EvalCandidate.created_at.desc())
    )
    return list(result.scalars().all())


async def confirm_candidate(
    db: AsyncSession, candidate_id: uuid.UUID, eval_set_id: uuid.UUID
) -> EvalSample:
    candidate = await db.get(EvalCandidate, candidate_id)
    if candidate is None or candidate.status != EvalCandidateStatus.PENDING.value:
        raise NotFoundError("候选不存在或已处理")
    await get_eval_set(db, eval_set_id)
    sample = EvalSample(
        eval_set_id=eval_set_id,
        question=candidate.question,
        expected_answer=candidate.expected_answer,
        expected_chunks=[],
        source=candidate.source,
    )
    candidate.status = EvalCandidateStatus.CONFIRMED.value
    db.add(sample)
    await db.commit()
    await db.refresh(sample)
    return sample


async def reject_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> None:
    candidate = await db.get(EvalCandidate, candidate_id)
    if candidate is None or candidate.status != EvalCandidateStatus.PENDING.value:
        raise NotFoundError("候选不存在或已处理")
    candidate.status = EvalCandidateStatus.REJECTED.value
    await db.commit()

