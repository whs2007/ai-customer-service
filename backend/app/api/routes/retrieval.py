"""检索测试接口（08 §6.2 / 05）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.core.response import ResponseModel, ok
from app.models.user import Role, User
from app.rag.retriever import run_retrieval_test
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval/test", response_model=ResponseModel[RetrievalResponse])
async def retrieval_test(
    payload: RetrievalRequest,
    _: User = Depends(require_roles(Role.ADMIN, Role.AGENT)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    data = await run_retrieval_test(
        db,
        kb_ids=payload.kb_ids,
        query=payload.query,
        top_k=payload.top_k,
        tags=payload.tags,
        retriever_mode=payload.retriever_mode,
    )
    return ok(data=data)

