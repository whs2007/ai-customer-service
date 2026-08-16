"""系统设置请求/响应模型（B6a）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.pipeline.chunker import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP


class PromptConfig(BaseModel):
    """Prompt 配置（07 §2：系统人设 / 兜底话术 / 转人工判定规则）。"""

    system_prompt: str = Field(
        default=(
            "你是 AI 智能客服，回答需基于知识库引用，不得编造；"
            "引用来源用 [1][2] 编号标注。"
        ),
        max_length=2000,
    )
    fallback_text: str = Field(
        default="抱歉，我暂时无法回答这个问题。您可以尝试换个问法，或转人工客服。",
        max_length=500,
    )
    escalation_rule_text: str = Field(
        default="连续 2 次无法回答或用户投诉/明确要求转人工时，转人工并创建工单。",
        max_length=500,
    )


class EscalationConfig(BaseModel):
    """客服规则（07 §2：转人工条件 + 工单优先级规则）。"""

    threshold: int = Field(default=2, ge=1, le=10, description="连续兜底次数触发转人工")
    priority_rules: dict[str, str] = Field(
        default_factory=lambda: {"complaint": "high", "transfer": "medium", "other": "medium"},
        description="意图 → 工单优先级",
    )


class ChunkingConfig(BaseModel):
    """数据管理（07 §2：普通文本分块参数，04 §3.5）。"""

    # 单一默认值来源：与 pipeline.chunker 保持一致，避免两处漂移
    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=100, le=2000)
    overlap: int = Field(default=DEFAULT_OVERLAP, ge=0, le=200)


class ChannelConfigOut(BaseModel):
    """渠道配置（11 §8 / 开发文档 01 §6.2）：用户端默认知识库等。"""

    model_config = ConfigDict(from_attributes=True)

    channel: str
    default_kb_ids: list[str] = Field(default_factory=list)
    allow_human: bool = True
    business_hours: dict[str, Any] | None = None
    updated_at: datetime | None = None


class ChannelConfigUpdate(BaseModel):
    """渠道配置更新请求。"""

    channel: str = Field(pattern="^[a-zA-Z0-9_]{1,50}$", description="渠道标识")
    default_kb_ids: list[str] = Field(default_factory=list, max_length=20)
    allow_human: bool = True
    business_hours: dict[str, Any] | None = None
