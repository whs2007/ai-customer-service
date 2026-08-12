"""清理存量空 assistant 消息（B6b 审查 P2-10）。

空气泡修复前遗留数据：role=assistant 且 content='' 的消息。
用法：python scripts/cleanup_empty_messages.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, func, select

from app.db.session import get_session_factory
from app.models.message import Message


async def main() -> None:
    async with get_session_factory()() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.role == "assistant", Message.content == "")
        )
        await db.execute(
            delete(Message).where(
                Message.role == "assistant", Message.content == ""
            )
        )
        await db.commit()
        print(f"已清理空 assistant 消息：{count} 条")


if __name__ == "__main__":
    asyncio.run(main())

