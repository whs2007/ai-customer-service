"""用户端响应模型（11 §10 / 开发文档 01 §3：最小字段、不含内部字段）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserMessageOut(BaseModel):
    """用户端可见消息：仅 id/role/content/created_at（无 intent/cited_chunk_ids/trace）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class UserSessionOut(BaseModel):
    """用户端会话详情基础信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    channel: str
    created_at: datetime
    updated_at: datetime


class UserSessionListItem(BaseModel):
    """用户端会话列表项（12 §3.2）。"""

    id: uuid.UUID
    status: str
    updated_at: datetime
    message_count: int = 0
    last_message: str = ""
    ticket_no: str | None = None


class UserSessionDetailOut(BaseModel):
    """用户端会话详情（12 §3.2）：消息脱敏。"""

    session: UserSessionOut
    messages: list[UserMessageOut] = Field(default_factory=list)


class UserTicketOut(BaseModel):
    """用户端工单列表项（12 §4.1）。"""

    id: uuid.UUID
    ticket_no: str
    status: str
    priority: str
    session_id: uuid.UUID
    claimed_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RatingOut(BaseModel):
    """工单满意度评价（11 §4.4 / P2 预留接口）。"""

    score: int
    comment: str | None = None


class UserTicketDetailOut(BaseModel):
    """用户端工单详情：工单 + 会话完整消息（脱敏）+ 评价状态。"""

    ticket: UserTicketOut
    messages: list[UserMessageOut] = Field(default_factory=list)
    rating: RatingOut | None = None
    can_rate: bool = False


class UserTicketRatingCreate(BaseModel):
    """用户端工单评价请求（P2 接口预留）。"""

    score: int = Field(ge=1, le=5, description="1~5 星")
    comment: str | None = Field(default=None, max_length=500)
