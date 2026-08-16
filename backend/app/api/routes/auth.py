"""认证与 RBAC 接口（08 §4.1 / §6.2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_roles
from app.core.exceptions import BadRequestError
from app.core.ratelimit import (
    enforce_login_rate_limit,
    enforce_refresh_rate_limit,
    enforce_register_rate_limit,
    generate_captcha,
)
from app.core.response import PageData, ResponseModel, ok
from app.models.user import Role, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserCreate,
    UserOut,
    UserPasswordReset,
    UserUpdate,
)
from app.services.audit_service import write_audit
from app.services.auth_service import (
    authenticate_user,
    change_password,
    refresh_tokens,
    register_user,
)
from app.services.user_service import create_user, list_users, reset_password, update_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/captcha", response_model=ResponseModel)
async def captcha() -> ResponseModel:
    """生成算术验证码（用户端注册防刷，12 §2.1）。【新增】验证码获取端点。"""
    challenge_id, question = generate_captcha()
    return ok(data={"captcha_id": challenge_id, "question": question})


@router.post("/register", response_model=ResponseModel)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """用户端自助注册：校验通过后直接返回令牌（自动登录）。"""
    await enforce_register_rate_limit(request)
    user, tokens = await register_user(
        db, payload, ip=_client_ip(request)
    )
    return ok(
        data={
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": "bearer",
            "user": UserOut.model_validate(user),
        },
        message="注册成功",
    )


@router.post("/login", response_model=ResponseModel[TokenPair])
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """账密登录，签发 access + refresh。"""
    await enforce_login_rate_limit(request)
    _, tokens = await authenticate_user(
        db, payload.username, payload.password, ip=_client_ip(request)
    )
    return ok(data=tokens, message="登录成功")


@router.post("/refresh", response_model=ResponseModel[TokenPair])
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """刷新令牌（轮换）。"""
    await enforce_refresh_rate_limit(request)
    tokens = await refresh_tokens(db, payload.refresh_token)
    return ok(data=tokens, message="刷新成功")


@router.get("/me", response_model=ResponseModel[UserOut])
async def me(user: User = Depends(get_current_user)) -> ResponseModel:
    """当前登录用户信息。"""
    return ok(data=UserOut.model_validate(user))


@router.put("/password", response_model=ResponseModel)
async def change_my_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    """用户端修改密码：成功后旧 token 全部失效，需重新登录。"""
    await change_password(db, user, payload.old_password, payload.new_password)
    return ok(message="密码已修改，请重新登录")


@router.get("/users", response_model=ResponseModel[PageData[UserOut]])
async def list_users_endpoint(
    _: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 10,
) -> ResponseModel:
    items, total = await list_users(db, page, page_size)  # noqa: F821 - 调用 service.list_users
    return ok(
        data=PageData[UserOut](
            items=[UserOut.model_validate(u) for u in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/users", response_model=ResponseModel[UserOut])
async def create_user_endpoint(
    payload: UserCreate,
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    user = await create_user(db, payload)
    await write_audit(
        db,
        action="user_create",
        user_id=str(admin.id),
        ip=request.client.host if request.client else None,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username, "role": user.role},
    )
    return ok(data=UserOut.model_validate(user), message="用户已创建")


@router.put("/users/{user_id}", response_model=ResponseModel[UserOut])
async def update_user_endpoint(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    if str(admin.id) == user_id and payload.status and payload.status.value == "disabled":
        raise BadRequestError("不能停用当前登录账号")
    user = await update_user(db, user_id, payload)
    await write_audit(
        db,
        action="user_update",
        user_id=str(admin.id),
        ip=request.client.host if request.client else None,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username, "role": user.role, "status": user.status},
    )
    return ok(data=UserOut.model_validate(user), message="用户已更新")


@router.put("/users/{user_id}/password", response_model=ResponseModel)
async def reset_user_password(
    user_id: str,
    payload: UserPasswordReset,
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel:
    user = await reset_password(db, user_id, payload.password)
    await write_audit(
        db,
        action="user_password_reset",
        user_id=str(admin.id),
        ip=request.client.host if request.client else None,
        target_type="user",
        target_id=str(user.id),
        detail={"username": user.username},
    )
    return ok(message="密码已重置")
