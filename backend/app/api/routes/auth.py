"""认证与 RBAC 接口（08 §4.1 / §6.2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_roles
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair, UserOut
from app.services.auth_service import authenticate_user, refresh_tokens

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=ResponseModel[TokenPair])
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """账密登录，签发 access + refresh。"""
    _, tokens = await authenticate_user(
        db, payload.username, payload.password, ip=_client_ip(request)
    )
    return ok(data=tokens, message="登录成功")


@router.post("/refresh", response_model=ResponseModel[TokenPair])
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """刷新令牌（轮换）。"""
    tokens = await refresh_tokens(db, payload.refresh_token)
    return ok(data=tokens, message="刷新成功")


@router.get("/me", response_model=ResponseModel[UserOut])
async def me(user: User = Depends(get_current_user)) -> ResponseModel:
    """当前登录用户信息。"""
    return ok(data=UserOut.model_validate(user))


@router.get("/users", response_model=ResponseModel[PageData[UserOut]])
async def list_users(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 10,
) -> ResponseModel:
    """用户列表（仅 admin；RBAC 骨架演示接口）。"""
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [UserOut.model_validate(u) for u in result.scalars().all()]
    return ok(data=PageData[UserOut](items=items, total=total, page=page, page_size=page_size))
