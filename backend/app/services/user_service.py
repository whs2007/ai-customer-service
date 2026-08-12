"""用户管理服务（B6a：账号权限 Tab）。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import UserCreate, UserUpdate


async def list_users(
    db: AsyncSession, page: int, page_size: int
) -> tuple[list[User], int]:
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    existing = await db.scalar(select(User).where(User.username == payload.username.strip()))
    if existing is not None:
        raise ConflictError("用户名已存在")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role=payload.role.value,
        status=payload.status.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession, user_id: uuid.UUID | str, payload: UserUpdate
) -> User:
    user_id = uuid.UUID(str(user_id))
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.role is not None:
        user.role = payload.role.value
    if payload.status is not None:
        user.status = payload.status.value
    await db.commit()
    await db.refresh(user)
    return user


async def reset_password(
    db: AsyncSession, user_id: uuid.UUID | str, new_password: str
) -> User:
    user_id = uuid.UUID(str(user_id))
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    user.password_hash = hash_password(new_password)
    await db.commit()
    await db.refresh(user)
    return user
