"""敏感数据脱敏（08 §5.3/§8：日志与审计中手机号、订单号、API Key 脱敏）。"""

from __future__ import annotations

import json
import re
from typing import Any

# 手机号：11 位，1 开头（前 3 保留 + 后 2 保留）
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
# 订单号：15 位纯数字（前 4 保留 + 后 4 保留）
_ORDER_RE = re.compile(r"(?<!\d)(\d{15})(?!\d)")
# API Key：sk- 开头的长串
_KEY_RE = re.compile(r"(sk-[A-Za-z0-9]{8,})")


def mask_phone(match: re.Match[str]) -> str:
    raw = match.group(1)
    return f"{raw[:3]}******{raw[-2:]}"


def mask_order(match: re.Match[str]) -> str:
    raw = match.group(1)
    return f"{raw[:4]}*******{raw[-4:]}"


def mask_key(match: re.Match[str]) -> str:
    raw = match.group(1)
    return f"{raw[:3]}***"


def mask_sensitive(text: str) -> str:
    """对文本中的手机号 / 15 位订单号 / sk- API Key 做部分打码。"""
    if not text:
        return text
    out = _PHONE_RE.sub(mask_phone, text)
    out = _ORDER_RE.sub(mask_order, out)
    out = _KEY_RE.sub(mask_key, out)
    return out


def mask_object(value: Any) -> Any:
    """对任意可 JSON 序列化对象递归脱敏（trace/审计 detail 使用）。"""
    if isinstance(value, str):
        return mask_sensitive(value)
    if isinstance(value, list):
        return [mask_object(v) for v in value]
    if isinstance(value, dict):
        return {k: mask_object(v) for k, v in value.items()}
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return mask_sensitive(str(value))
