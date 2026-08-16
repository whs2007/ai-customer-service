"""应用评测接口（08 §6.2 / 09）：仅 admin。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.schemas.evaluation import (
    CandidateConfirm,
    CandidateOut,
    EvalSetCreate,
    EvalSetOut,
    EvalTaskCreate,
    PassUpdate,
    SampleCreate,
    SampleImport,
    SampleOut,
)
from app.services import eval_service

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("/sets", response_model=ResponseModel[list[EvalSetOut]])
async def list_sets(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await eval_service.list_eval_sets(db))


@router.post("/sets", response_model=ResponseModel[EvalSetOut])
async def create_set(
    payload: EvalSetCreate,
    user: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    es = await eval_service.create_eval_set(db, payload, user)
    return ok(
        data=EvalSetOut(
            id=es.id,
            name=es.name,
            description=es.description,
            source=es.source,
            created_at=es.created_at,
            updated_at=es.updated_at,
        ),
        message="创建成功",
    )


@router.put("/sets/{set_id}", response_model=ResponseModel[EvalSetOut])
async def update_set(
    set_id: uuid.UUID,
    payload: EvalSetCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    es = await eval_service.update_eval_set(db, set_id, payload)
    return ok(
        data=EvalSetOut(
            id=es.id,
            name=es.name,
            description=es.description,
            source=es.source,
            created_at=es.created_at,
            updated_at=es.updated_at,
        ),
        message="更新成功",
    )


@router.delete("/sets/{set_id}", response_model=ResponseModel)
async def delete_set(
    set_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await eval_service.delete_eval_set(db, set_id)
    return ok(message="删除成功")


@router.get("/sets/{set_id}/samples", response_model=ResponseModel[PageData[SampleOut]])
async def list_samples(
    set_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await eval_service.list_samples(db, set_id, page, page_size)
    return ok(
        data=PageData[SampleOut](
            items=[SampleOut.model_validate(s) for s in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/sets/{set_id}/samples", response_model=ResponseModel[SampleOut])
async def add_sample(
    set_id: uuid.UUID,
    payload: SampleCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    sample = await eval_service.add_sample(db, set_id, payload)
    return ok(data=SampleOut.model_validate(sample), message="样本已添加")


@router.post("/sets/{set_id}/samples/import", response_model=ResponseModel)
async def import_samples(
    set_id: uuid.UUID,
    payload: SampleImport,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    count = await eval_service.import_samples(db, set_id, payload.items)
    return ok(message=f"成功导入 {count} 条样本")


@router.post("/sets/{set_id}/samples/import-public", response_model=ResponseModel)
async def import_public(
    set_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    count = await eval_service.import_public_samples(db, set_id)
    return ok(message=f"成功导入 {count} 条公开样例")


@router.get("/tasks", response_model=ResponseModel[PageData[dict]])
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items, total = await eval_service.list_eval_tasks(db, page, page_size)
    return ok(data=PageData[dict](items=items, total=total, page=page, page_size=page_size))


@router.post("/tasks", response_model=ResponseModel[dict])
async def create_task(
    payload: EvalTaskCreate,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    task = await eval_service.create_eval_task(db, payload, user)
    background_tasks.add_task(eval_service.process_eval_task_job, str(task.id))
    return ok(data=await eval_service.get_eval_task(db, task.id), message="评测任务已创建")


@router.get("/tasks/{task_id}", response_model=ResponseModel[dict])
async def get_task(
    task_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await eval_service.get_eval_task(db, task_id))


@router.post("/tasks/{task_id}/rerun", response_model=ResponseModel[dict])
async def rerun_task(
    task_id: uuid.UUID,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    task = await eval_service.rerun_eval_task(db, task_id)
    background_tasks.add_task(eval_service.process_eval_task_job, str(task.id))
    return ok(data=await eval_service.get_eval_task(db, task_id), message="已重新运行")


@router.delete("/tasks/{task_id}", response_model=ResponseModel)
async def delete_task(
    task_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await eval_service.delete_eval_task(db, task_id)
    return ok(message="删除成功")


@router.get("/tasks/{task_id}/report", response_model=ResponseModel)
async def get_report(
    task_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    return ok(data=await eval_service.get_report(db, task_id))


@router.put("/results/{result_id}/passed", response_model=ResponseModel)
async def update_passed(
    result_id: uuid.UUID,
    payload: PassUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await eval_service.update_result_passed(db, result_id, payload.passed)
    return ok(message="通过状态已更新")


@router.get("/candidates", response_model=ResponseModel[list[CandidateOut]])
async def list_candidates(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    items = await eval_service.list_candidates(db)
    return ok(data=[CandidateOut.model_validate(c) for c in items])


@router.post("/candidates/{candidate_id}/confirm", response_model=ResponseModel)
async def confirm_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateConfirm,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    sample = await eval_service.confirm_candidate(db, candidate_id, payload.eval_set_id)
    return ok(message=f"候选已确认并加入评测集（样本 {sample.id}）")


@router.post("/candidates/{candidate_id}/reject", response_model=ResponseModel)
async def reject_candidate(
    candidate_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await eval_service.reject_candidate(db, candidate_id)
    return ok(message="候选已拒绝")
