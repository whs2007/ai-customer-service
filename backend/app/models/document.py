"""文档模型（08 §5.2 documents 表）。

【新增】deleted_at：知识库软删除时级联标记文档，保持与 08 §4.2 删除语义一致。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploading','parsing','embedding','completed','failed')",
            name="ck_documents_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="文件名")
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="扩展名")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="字节数")
    file_url: Mapped[str] = mapped_column(String(500), nullable=False, comment="存储路径")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="uploading", comment="解析状态"
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="失败原因"
    )
    chunk_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0", comment="Chunk 数"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="软删除时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

