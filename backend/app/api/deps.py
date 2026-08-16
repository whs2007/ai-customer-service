"""依赖注入：当前用户、RBAC、数据库会话（08 §3.4 app/api/deps.py）。"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import get_db
from app.models.user import Role, User, UserStatus


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise UnauthorizedError("未登录")
    return auth_header[7:].strip()


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    """解析 Bearer token 并加载当前用户。"""
    token = _extract_token(request)
    payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("无效的登录凭证")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedError("账号不可用，请重新登录")
    if payload.get("ver") != user.token_version:
        raise UnauthorizedError("登录状态已失效，请重新登录")
    return user


def require_roles(*roles: Role):
    """RBAC 路由级依赖（08 §4.1）：当前用户角色必须命中其一。"""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in {role.value for role in roles}:
            raise ForbiddenError("无权限执行此操作")
        return user

    return _checker


def require_ticket_operator():
    """工单写操作权限（职责分离）：agent 可操作；admin 默认只读，
    仅当 allow_admin_ticket_ops=true 时允许（需求决策：管理端不伸手一线客服工作）。"""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role == "agent":
            return user
        if user.role == "admin" and get_settings().allow_admin_ticket_ops:
            return user
        raise ForbiddenError("工单处理仅客服可操作，管理员默认只读")

    return _checker
