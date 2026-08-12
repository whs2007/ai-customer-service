"""应用评测请求/响应模型（08 §4.9 / 09）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class EvalSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="名称（唯一，≤100 字）")
    description: str = Field(default="", max_length=200)


class EvalSetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=200)


class EvalSetOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    source: str
    sample_count: int = 0
    created_at: datetime
    updated_at: datetime


class SampleCreate(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    expected_answer: str = Field(min_length=1, max_length=2000)
    expected_chunks: list[uuid.UUID] = Field(default_factory=list)


class SampleImport(BaseModel):
    items: list[SampleCreate] = Field(min_length=1, max_length=500)


class SampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    eval_set_id: uuid.UUID
    question: str
    expected_answer: str
    expected_chunks: list
    source: str
    created_at: datetime


class EvalTaskCreate(BaseModel):
    eval_set_id: uuid.UUID
    model_profile_id: uuid.UUID | None = None
    kb_ids: list[uuid.UUID] = Field(min_length=1, max_length=20, description="评测检索知识库")


class EvalTaskOut(BaseModel):
    id: uuid.UUID
    eval_set_id: uuid.UUID
    eval_set_name: str = ""
    model_profile_id: uuid.UUID | None = None
    model_name: str = ""
    kb_ids: list
    status: str
    progress: int
    total: int
    score_avg: Decimal | None = None
    metrics: dict | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class EvalResultOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    question: str
    expected_answer: str
    answer: str
    citations: list
    scores: dict
    passed: bool


class EvalReportOut(BaseModel):
    task: EvalTaskOut
    score_avg: Decimal | None = None
    pass_rate: float = 0.0
    total: int = 0
    passed_count: int = 0
    metrics: dict | None = None
    results: list[EvalResultOut] = []


class PassUpdate(BaseModel):
    passed: bool


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    expected_answer: str
    source: str
    source_id: str | None = None
    message_id: uuid.UUID | None = None
    status: str
    created_at: datetime


class CandidateConfirm(BaseModel):
    eval_set_id: uuid.UUID
