"""对话 / 会话 / 反馈 / 模型配置 请求响应模型（08 §4.4 / §6.2）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = Field(default=None, description="为空则新建会话")
    kb_ids: list[uuid.UUID] = Field(min_length=1, max_length=20, description="多知识库")
    message: str = Field(min_length=1, max_length=500, description="用户消息")
    model_profile_id: uuid.UUID | None = Field(default=None, description="临时指定模型")
    form_data: dict | None = Field(default=None, description="对话内表单收集结果")


class FeedbackCreate(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
    chunk_id: uuid.UUID = Field(description="目标引用 Chunk")
    action: Literal["delete", "invalid", "add"]
    reason: str | None = Field(default=None, max_length=200, description="标记无效原因")


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    channel: str
    kb_ids: list
    escalation_count: int
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    intent: str | None = None
    cited_chunk_ids: list
    created_at: datetime


class SessionDetailOut(BaseModel):
    session: SessionOut
    messages: list[MessageOut]


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    message_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    action: str
    reason: str | None = None
    created_at: datetime


class ModelProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    model: str
    base_url: str | None = None
    api_key: str = ""
    temperature: Decimal
    top_p: Decimal
    max_tokens: int
    role: str
    is_default: bool
    enabled: bool


class IntentRulesUpdate(BaseModel):
    keywords: dict[str, list[str]] | None = None
    order_no_pattern: str | None = Field(default=None, max_length=50)

