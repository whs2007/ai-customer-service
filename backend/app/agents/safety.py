"""Prompt 注入防护（08 §8：输入前置规则过滤）。

轻量规则层：命中越权/改指令关键词时，对话链路返回兜底话术，不进入图执行；
系统提示词另设强边界（见 nodes.py generate）。后续可扩展 LLM 判定。
"""

from __future__ import annotations

INJECTION_PATTERNS: tuple[str, ...] = (
    "忽略以上",
    "忽略之前",
    "忽略前面的",
    "忽略所有",
    "不要遵守",
    "不要理会",
    "无视",
    "系统提示",
    "系统指令",
    "提示词是什么",
    "你的指令",
    "你的规则",
    "扮演",
    "假装你是",
    "你现在是",
    "越权",
    "管理员权限",
    "后端接口",
    "数据库",
    "api key",
    "apikey",
    "泄露",
    "告诉我你的",
    "ignore previous",
    "ignore all",
    "disregard",
    "forget your",
    "system prompt",
    "you are now",
    "act as",
    "reveal your",
    "print your",
)


def check_prompt_injection(text: str) -> str | None:
    """返回命中的第一个关键词；未命中返回 None。"""
    lowered = (text or "").lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in lowered:
            return pattern
    return None
