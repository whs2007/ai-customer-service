"""日志告警占位（08 §9 告警规则）。

阈值：LLM 失败率 > 20%、5xx 比例 > 10%、队列积压 > 100、后台任务失败数 > 0。
当前以 warning 日志输出（占位），后续可接 Prometheus Alertmanager。
"""

from __future__ import annotations

import structlog

from app.core.metrics import (
    HTTP_REQUESTS,
    LLM_CALLS,
    LLM_FAILURES,
    QUEUE_LAG,
    TASK_FAILURES,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

LLM_FAILURE_RATE_THRESHOLD = 0.20
HTTP_5XX_RATE_THRESHOLD = 0.10
QUEUE_LAG_THRESHOLD = 100


def _counter_value(counter) -> float:
    try:
        return float(counter._value.get())  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return 0.0


def check_alerts() -> None:
    """按阈值输出告警日志（占位；不阻塞业务）。"""
    llm_total = _counter_value(LLM_CALLS)
    if llm_total > 0:
        llm_fail = _counter_value(LLM_FAILURES)
        rate = llm_fail / llm_total
        if rate > LLM_FAILURE_RATE_THRESHOLD:
            logger.warning(
                "ALERT llm_failure_rate_high",
                rate=round(rate, 3),
                threshold=LLM_FAILURE_RATE_THRESHOLD,
            )

    http_total = _counter_value(HTTP_REQUESTS)
    if http_total > 0:
        # HTTP_REQUESTS 为多维 Counter，统计 5xx 需遍历
        samples = list(HTTP_REQUESTS.collect())
        total = 0
        err5 = 0
        for metric in samples:
            for sample in metric.samples:
                total += int(sample.value)
                if sample.labels.get("status", "").startswith("5"):
                    err5 += int(sample.value)
        if total > 0 and err5 / total > HTTP_5XX_RATE_THRESHOLD:
            logger.warning(
                "ALERT http_5xx_rate_high",
                rate=round(err5 / total, 3),
                threshold=HTTP_5XX_RATE_THRESHOLD,
            )

    lag = QUEUE_LAG._value.get()  # noqa: SLF001
    if lag and lag > QUEUE_LAG_THRESHOLD:
        logger.warning("ALERT queue_lag_high", lag=lag, threshold=QUEUE_LAG_THRESHOLD)

    task_fail = _counter_value(TASK_FAILURES)
    if task_fail > 0:
        logger.warning("ALERT background_task_failures", count=task_fail)

