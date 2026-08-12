"""内容审核（可插拔，08 §8 内容安全）。

优先调用外部审核 API（配置 MODERATION_API_URL/KEY）；未配置时使用
本地敏感词兜底（词表存 settings group=moderation，可配置覆盖）。
"""

from __future__ import annotations

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.settings_service import get_setting, set_setting

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# 本地敏感词兜底（通用违禁词占位；可通过 settings 覆盖）
DEFAULT_SENSITIVE_WORDS = ["赌博", "博彩", "色情", "毒品", "违禁", "诈骗", "洗钱", "枪支"]


async def get_sensitive_words(db: AsyncSession) -> list[str]:
    setting = await get_setting(db, "sensitive_words")
    if setting and setting.group == "moderation" and isinstance(setting.value, list):
        return [str(w) for w in setting.value if w]
    return DEFAULT_SENSITIVE_WORDS


async def set_sensitive_words(db: AsyncSession, words: list[str]) -> None:
    cleaned = list(dict.fromkeys(w.strip() for w in words if w.strip()))[:200]
    await set_setting(
        db,
        key="sensitive_words",
        value=cleaned,
        group="moderation",
        description="本地敏感词兜底（内容审核）",
    )


async def check_text(db: AsyncSession, text: str) -> dict:
    """返回 {"blocked": bool, "matched": str|None}。"""
    settings = get_settings()
    if not settings.moderation_enabled:
        return {"blocked": False, "matched": None}
    if settings.moderation_api_url:
        result = await _check_via_api(text)
        if result is not None:
            return result
    words = await get_sensitive_words(db)
    for word in words:
        if word and word in text:
            return {"blocked": True, "matched": word}
    return {"blocked": False, "matched": None}


async def _check_via_api(text: str) -> dict | None:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.moderation_api_url,
                headers={
                    "Authorization": f"Bearer {settings.moderation_api_key}"
                }
                if settings.moderation_api_key
                else {},
                json={"text": text},
            )
            resp.raise_for_status()
            data = resp.json()
            blocked = bool(data.get("blocked", data.get("hit", False)))
            return {"blocked": blocked, "matched": data.get("matched")}
    except Exception as exc:  # noqa: BLE001
        # 外部审核失败回退本地兜底；日志不记录 Key
        logger.warning("moderation_api_fallback", error=str(exc)[:200])
        return None
