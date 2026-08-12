"""通用分页参数（08 §6.1）。"""

from __future__ import annotations

from fastapi import Query
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


def pagination_params(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页条数，≤100"),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)

