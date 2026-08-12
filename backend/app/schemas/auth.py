"""认证相关请求/响应（08 §4.1 / §6.2）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import Role, UserStatus


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50, description="登录名")
    password: str = Field(min_length=1, max_length=128, description="密码")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, description="刷新令牌")


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """当前用户信息（不含密码哈希）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    status: str
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50, description="登录名")
    password: str = Field(min_length=6, max_length=128, description="初始密码")
    display_name: str = Field(min_length=1, max_length=50)
    role: Role = Role.VIEWER
    status: UserStatus = UserStatus.ACTIVE


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    role: Role | None = None
    status: UserStatus | None = None


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=6, max_length=128, description="新密码")
