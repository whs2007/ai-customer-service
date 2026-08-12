"""Chunk 接口（04 §4）：列表、新增、编辑、删除。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.schemas.knowledge import ChunkCreate, ChunkOut, ChunkUpdate
from app.services import chunk_service, document_service

router = APIRouter(tags=["chunks"])


@router.get("/documents/{doc_id}/chunks", response_model=ResponseModel[PageData[ChunkOut]])
async def list_chunks(
    doc_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await document_service.get_document(db, doc_id)
    items, total = await chunk_service.list_chunks(db, doc_id, page, page_size)
    return ok(
        data=PageData[ChunkOut](
            items=[ChunkOut.model_validate(c) for c in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/chunks", response_model=ResponseModel[ChunkOut])
async def create_chunk(
    payload: ChunkCreate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    chunk = await chunk_service.create_chunk(db, payload)
    return ok(data=ChunkOut.model_validate(chunk), message="已添加 Chunk")


@router.get("/chunks/{chunk_id}", response_model=ResponseModel[ChunkOut])
async def get_chunk(
    chunk_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    chunk = await chunk_service.get_chunk(db, chunk_id)
    return ok(data=ChunkOut.model_validate(chunk))


@router.put("/chunks/{chunk_id}", response_model=ResponseModel[ChunkOut])
async def update_chunk(
    chunk_id: uuid.UUID,
    payload: ChunkUpdate,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    chunk = await chunk_service.update_chunk(db, chunk_id, payload)
    return ok(data=ChunkOut.model_validate(chunk), message="已更新，正在重新向量化")


@router.delete("/chunks/{chunk_id}", response_model=ResponseModel)
async def delete_chunk(
    chunk_id: uuid.UUID,
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    await chunk_service.delete_chunk(db, chunk_id)
    return ok(message="删除成功")

