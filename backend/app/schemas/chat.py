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
    include_in_eval: bool = Field(default=False, description="标记纳入评测集（生成候选）")


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    channel: str
    kb_ids: list
    escalation_count: int
    created_at: datetime
    updated_at: datetime


class SessionListItemOut(BaseModel):
    """会话列表项（10 §4.1：含消息数/意图/是否转人工/工单号/标注状态）。"""

    id: uuid.UUID
    status: str
    channel: str
    kb_ids: list
    escalation_count: int
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    intent: str | None = None
    transferred: bool = False
    ticket_no: str | None = None
    annotated: bool = False


class TraceStepOut(BaseModel):
    step: str
    latency_ms: int = 0
    detail: dict | None = None


class TraceOut(BaseModel):
    request_id: str
    steps: list[TraceStepOut] = []
    latency_ms: int = 0
    created_at: datetime


class TicketBriefOut(BaseModel):
    id: uuid.UUID
    ticket_no: str
    status: str
    priority: str
    created_at: datetime


class AnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    tags: list
    note: str
    include_in_eval: bool
    eval_set_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class AnnotationCreate(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=10, description="标签（多选）")
    note: str = Field(default="", max_length=500, description="备注")
    include_in_eval: bool = Field(default=False, description="纳入评测集")
    eval_set_id: uuid.UUID | None = Field(default=None, description="目标评测集（可选）")


class CitationOut(BaseModel):
    """引用明细（08 §4.3 返回字段；会话恢复时从 chunks 反查，10 §4.2）。"""

    chunk_id: uuid.UUID
    kb_id: uuid.UUID
    document_name: str
    page: str | None = None
    row: str | None = None
    question: str = ""
    answer: str = ""
    retrieval_score: float | None = None
    rerank_score: float | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    intent: str | None = None
    cited_chunk_ids: list
    citations: list[CitationOut] = Field(default_factory=list)
    created_at: datetime


class SessionDetailOut(BaseModel):
    session: SessionOut
    messages: list[MessageOut]
    trace: TraceOut | None = None
    ticket: TicketBriefOut | None = None
    annotation: AnnotationOut | None = None


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


class ModelProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50, description="配置名称（唯一）")
    provider: str = Field(min_length=1, max_length=20)
    model: str = Field(min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=255)
    api_key: str = Field(default="", max_length=500, description="新增必填；编辑留空不修改")
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, ge=0, le=1)
    max_tokens: int = Field(default=2048, ge=1, le=100000)
    role: Literal["chat", "embedding", "rerank"] = "chat"
    is_default: bool = False
    enabled: bool = True


class ModelProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    provider: str | None = Field(default=None, min_length=1, max_length=20)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=500, description="留空表示不修改")
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=100000)
    role: Literal["chat", "embedding", "rerank"] | None = None
    enabled: bool | None = None


class ModelProfileTestOut(BaseModel):
    ok: bool
    latency_ms: int | None = None
    message: str = ""


class IntentRulesUpdate(BaseModel):
    keywords: dict[str, list[str]] | None = None
    order_no_pattern: str | None = Field(default=None, max_length=50)
