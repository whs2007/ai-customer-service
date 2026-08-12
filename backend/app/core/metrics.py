"""Prometheus 指标（08 §9 可观测）。

覆盖：HTTP 延迟/错误率、LLM token 与成本、检索 P95、队列积压量。
挂载于 GET /metrics（Prometheus 文本格式）。
"""

from __future__ import annotations

import re

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# HTTP
HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP 请求数", ["method", "path", "status"]
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP 请求耗时", ["method", "path"]
)

# LLM（08 §9：token 消耗与成本）
LLM_CALLS = Counter("llm_calls_total", "LLM 调用次数", ["provider", "model"])
LLM_TOKENS = Counter("llm_tokens_total", "LLM token 消耗", ["kind"])
LLM_FAILURES = Counter("llm_failures_total", "LLM 调用失败次数", ["provider", "model"])
LLM_COST = Counter("llm_cost_total", "LLM 成本估算", ["currency"])

# 检索
RETRIEVAL_REQUESTS = Counter("retrieval_requests_total", "检索请求数")
RETRIEVAL_DURATION = Histogram("retrieval_duration_seconds", "检索耗时")

# 队列 / 任务
QUEUE_LAG = Gauge("queue_lag", "Celery 队列积压量（inline 模式为 0）")
TASK_FAILURES = Counter("task_failures_total", "后台任务失败数", ["kind"])


def normalize_path(path: str) -> str:
    """路径归一化：UUID 段替换为 :id，避免指标基数爆炸。"""
    return re.sub(r"/[0-9a-fA-F-]{36}", "/:id", path)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

