"""FastAPI 应用入口。

对应需求文档 08 §3.4 的目录结构；B1 阶段仅提供：
- 统一响应与错误码（08 §7）
- JWT 登录与 RBAC 骨架（users 表 + admin/agent/viewer 角色）
- Redis 连接（降级不阻塞启动）
- structlog 结构化日志
- /health 健康检查
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    admin,
    agent,
    auth,
    chat,
    chunks,
    dashboard,
    documents,
    evaluations,
    events,
    feedbacks,
    health,
    knowledge_bases,
    retrieval,
    sessions,
    tickets,
    user,
)
from app.api.routes import (
    settings as settings_router,
)
from app.core.config import get_settings
from app.core.exceptions import AppError, InternalError
from app.core.logging import configure_logging
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS, normalize_path
from app.core.redis import close_redis, init_redis
from app.core.response import ResponseModel
from app.services.event_service import start_event_relay, stop_event_relay

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化 Redis 连接（失败仅告警，不阻塞启动）。"""
    settings = get_settings()
    await init_redis(settings)
    await start_event_relay()
    logger.info("application_started", app=settings.app_name, version=settings.version)
    try:
        yield
    finally:
        await stop_event_relay()
        await close_redis()
        logger.info("application_stopped", app=settings.app_name)


def create_app() -> FastAPI:
    """应用工厂：便于测试与后续拆分部署。"""
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.json_logs)

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="AI 智能客服系统管理端后端 API（B1 基建骨架）",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.debug else None,
    )

    # CORS：仅允许配置的前端来源（01 §2 / 08 §8）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由：/api 前缀（08 §6.1）
    app.include_router(health.router)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(knowledge_bases.router, prefix=settings.api_prefix)
    app.include_router(documents.router, prefix=settings.api_prefix)
    app.include_router(chunks.router, prefix=settings.api_prefix)
    app.include_router(retrieval.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)
    app.include_router(feedbacks.router, prefix=settings.api_prefix)
    app.include_router(settings_router.router, prefix=settings.api_prefix)
    app.include_router(evaluations.router, prefix=settings.api_prefix)
    app.include_router(tickets.router, prefix=settings.api_prefix)
    app.include_router(dashboard.router, prefix=settings.api_prefix)
    app.include_router(sessions.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    app.include_router(user.router, prefix=settings.api_prefix)
    app.include_router(agent.router, prefix=settings.api_prefix)
    app.include_router(events.router, prefix=settings.api_prefix)

    # 统一异常处理（08 §7 错误码规范）
    register_exception_handlers(app)

    # 请求日志中间件（含 request_id，为全链路可观测打底，08 §9）
    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            structlog.contextvars.bind_contextvars(
                method=request.method, path=request.url.path
            )
            logger.info("request_start")
            started = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("request_error")
                raise
            duration = time.perf_counter() - started
            HTTP_REQUESTS.labels(
                method=request.method,
                path=normalize_path(request.url.path),
                status=str(response.status_code),
            ).inc()
            HTTP_DURATION.labels(
                method=request.method, path=normalize_path(request.url.path)
            ).observe(duration)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_end", status_code=response.status_code
            )
            return response

    return app


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=ResponseModel(code=exc.code, message=exc.message, data=exc.detail).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        detail: list[dict[str, Any]] = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []))
            detail.append({"field": loc, "message": err.get("msg", "")})
        return JSONResponse(
            status_code=422,
            content=ResponseModel(
                code=42200, message="请求参数校验失败", data=detail
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code_map = {401: 40100, 403: 40300, 404: 40400, 409: 40900}
        return JSONResponse(
            status_code=exc.status_code,
            content=ResponseModel(
                code=code_map.get(exc.status_code, exc.status_code * 100),
                message=str(exc.detail),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", exc_info=exc)
        err = InternalError()
        return JSONResponse(
            status_code=err.http_status,
            content=ResponseModel(code=err.code, message=err.message).model_dump(),
        )


app = create_app()
