"""structlog 结构化日志配置（08 §9 可观测性）。"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.dev import ConsoleRenderer


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """配置 structlog 与标准库日志。

    - json_logs=True：JSON 输出（生产/容器环境）
    - json_logs=False：控制台彩色输出（本地开发）
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
