"""统一业务异常（08 §7 错误码规范）。"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """业务异常基类：code 为业务错误码，http_status 为 HTTP 状态码。"""

    code: int = 50000
    http_status: int = 500

    def __init__(self, message: str = "", data: Any = None):
        self.message = message or self.__class__.__doc__ or "内部错误"
        self.detail = data
        super().__init__(self.message)


class BadRequestError(AppError):
    """参数错误"""

    code = 40000
    http_status = 400


class UnauthorizedError(AppError):
    """未登录"""

    code = 40100
    http_status = 401


class TokenExpiredError(AppError):
    """token 过期"""

    code = 40101
    http_status = 401


class ForbiddenError(AppError):
    """无权限"""

    code = 40300
    http_status = 403


class NotFoundError(AppError):
    """资源不存在"""

    code = 40400
    http_status = 404


class ConflictError(AppError):
    """冲突（名称重复等）"""

    code = 40900
    http_status = 409


class ValidationFailedError(AppError):
    """校验失败"""

    code = 42200
    http_status = 422


class InternalError(AppError):
    """内部错误"""

    code = 50000
    http_status = 500


class UpstreamError(AppError):
    """上游服务错误（LLM/检索）"""

    code = 50200
    http_status = 502


class UpstreamTimeoutError(AppError):
    """上游超时"""

    code = 50400
    http_status = 504

