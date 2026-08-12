"""LLM-as-judge 打分（08 §4.9 / 09 §5）。

指标：回答准确性（先行实现）；问题相关性 / 语义准确性字段预留。
配置 LLM_API_KEY 时调用真实模型打分；未配置时用确定性 bigram 重合度（可复现）。
"""

from __future__ import annotations

import json
import re

import httpx
import structlog

from app.core.config import Settings, get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

PASS_THRESHOLD = 60  # 通过阈值（百分比）


def _bigrams(text: str) -> set[str]:
    chars = [c for c in text if not c.isspace()]
    grams = set(chars)
    grams.update(f"{a}{b}" for a, b in zip(chars, chars[1:]))
    return grams


def accuracy_heuristic(expected: str, answer: str) -> float:
    """确定性相似度：期望答案与模型回答的字符 bigram Jaccard × 100。"""
    if not answer or not expected:
        return 0.0
    e, a = _bigrams(expected), _bigrams(answer)
    union = e | a
    if not union:
        return 0.0
    return round(len(e & a) / len(union) * 100, 2)


async def judge_answer(
    question: str,
    expected: str,
    answer: str,
    model_name: str = "",
    settings: Settings | None = None,
) -> dict:
    """返回 {"accuracy": 0-100, "relevancy": None, "semantic": None}。"""
    settings = settings or get_settings()
    accuracy = None
    if settings.llm_api_key:
        accuracy = await _judge_via_llm(
            question, expected, answer, model_name, settings
        )
    if accuracy is None:
        accuracy = accuracy_heuristic(expected, answer)
    return {"accuracy": accuracy, "relevancy": None, "semantic": None}


async def _judge_via_llm(
    question: str,
    expected: str,
    answer: str,
    model_name: str,
    settings: Settings,
) -> float | None:
    prompt = (
        "你是评测裁判。请仅输出 JSON：{\"accuracy\": 0-100 整数}，"
        "表示模型回答与期望答案的语义一致度（回答准确性）。\n"
        f"问题：{question}\n期望答案：{expected}\n模型回答：{answer}"
    )
    base_url = (settings.llm_base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": model_name or settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        match = re.search(r"(\d{1,3})", content)
        if match:
            return max(0.0, min(100.0, float(match.group(1))))
    except Exception as exc:  # noqa: BLE001
        # 日志不记录 Key；打分失败回退启发式，保证评测可完成
        logger.warning("judge_llm_fallback", error=str(exc)[:200])
    return None

