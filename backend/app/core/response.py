"""统一响应模型（08 §6.1：{"code": 0, "message": "ok", "data": {...}}）。"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """统一响应包裹。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


class PageData(BaseModel, Generic[T]):
    """分页数据（08 §6.1）。"""

    items: list[T]
    total: int
    page: int
    page_size: int


def ok(data: Any = None, message: str = "ok") -> ResponseModel:
    return ResponseModel(code=0, message=message, data=data)
