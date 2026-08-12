"""知识库 / 文档 / Chunk 请求与响应模型（08 §5.2 / §6.2）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_tags(tags: list[str] | None) -> list[str]:
    """标签清洗：去空白、去重、单标签 ≤20 字、最多 10 个（04 §4.5 新增规则）。"""
    if not tags:
        return []
    cleaned: list[str] = []
    for tag in tags:
        tag = (tag or "").strip()
        if not tag:
            continue
        tag = tag[:20]
        if tag not in cleaned:
            cleaned.append(tag)
    return cleaned[:10]


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50, description="名称（唯一，≤50 字）")
    description: str = Field(default="", max_length=200, description="描述（≤200 字）")


class KnowledgeBaseUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    doc_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseDetailOut(BaseModel):
    """详情在列表字段基础上附加创建人。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kb_id: uuid.UUID
    file_name: str
    file_type: str
    file_size: int
    status: str
    error_message: str | None = None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class UploadDocumentOut(BaseModel):
    document_id: uuid.UUID
    file_name: str
    status: str


class ChunkCreate(BaseModel):
    doc_id: uuid.UUID
    question: str = Field(min_length=1, max_length=200, description="问题（必填，≤200 字）")
    answer: str = Field(min_length=1, max_length=2000, description="答案（必填，≤2000 字）")
    category: str | None = Field(default=None, max_length=50, description="分类")
    tags: list[str] = Field(default_factory=list, description="标签（最多 10 个，单个 ≤20 字）")
    page: str | None = Field(default=None, max_length=50)
    row: str | None = Field(default=None, max_length=50)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return _clean_tags(v)

    @field_validator("category")
    @classmethod
    def strip_category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v[:50] or None


class ChunkUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=200)
    answer: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, max_length=50)
    tags: list[str] | None = Field(default=None)
    page: str | None = Field(default=None, max_length=50)
    row: str | None = Field(default=None, max_length=50)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        return _clean_tags(v) if v is not None else None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_id: uuid.UUID
    kb_id: uuid.UUID
    chunk_index: int
    question: str
    answer: str
    category: str | None = None
    page: str | None = None
    row: str | None = None
    word_count: int
    tags: list[str]
    created_at: datetime
    updated_at: datetime

