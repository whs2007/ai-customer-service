"""运维命令行工具（08 §8：初始管理员引导，替代迁移硬编码种子）。

用法：
    python -m app.cli bootstrap        # 按环境变量引导初始管理员
    python -m app.cli create-admin --username admin --password <pwd> [--display-name 管理员]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models.user import Role, User

logger = structlog.get_logger(__name__)


async def _admin_exists(db) -> bool:
    count = await db.scalar(
        select(func.count()).select_from(User).where(User.role == Role.ADMIN.value)
    )
    return bool(count)


async def _create_admin(username: str, password: str, display_name: str) -> User:
    async with get_session_factory()() as db:
        exists = await db.scalar(
            select(User).where(User.username == username.strip())
        )
        if exists is not None:
            logger.info("admin_already_exists", username=username)
            return exists
        user = User(
            username=username.strip(),
            password_hash=hash_password(password),
            display_name=display_name.strip() or "管理员",
            role=Role.ADMIN.value,
            status="active",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("admin_created", username=user.username)
        return user


async def _bootstrap() -> int:
    """引导初始管理员：
    - 已存在管理员：跳过；
    - 配置了 ADMIN_INITIAL_PASSWORD：按配置创建（生产推荐）；
    - 生产环境未配置：报错退出（fail-closed，避免无管理员可用却静默成功）；
    - 开发/测试环境：创建 admin/admin123 并告警（仅本地便利）。
    """
    settings = get_settings()
    async with get_session_factory()() as db:
        if await _admin_exists(db):
            logger.info("admin_bootstrap_skipped", reason="admin_exists")
            return 0

    password = settings.admin_initial_password.strip()
    if password:
        await _create_admin(
            settings.admin_username, password, settings.admin_display_name
        )
        return 0

    if settings.environment == "production":
        logger.error(
            "admin_bootstrap_required",
            message="未发现管理员且未配置 ADMIN_INITIAL_PASSWORD，"
            "请设置该环境变量后重试（生产环境禁止使用默认口令）",
        )
        return 1

    # 开发/测试便利：创建默认 admin，并明确告警
    await _create_admin(settings.admin_username, "admin123", settings.admin_display_name)
    logger.warning(
        "admin_bootstrap_dev_default",
        message="开发环境已创建默认管理员 admin/admin123，请勿用于生产",
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 智能客服系统运维工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="引导初始管理员（读取 ADMIN_* 环境变量）")

    create = sub.add_parser("create-admin", help="显式创建管理员")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--display-name", default="管理员")

    args = parser.parse_args()
    if args.command == "create-admin":
        asyncio.run(
            _create_admin(args.username, args.password, args.display_name)
        )
        return
    sys.exit(asyncio.run(_bootstrap()))


if __name__ == "__main__":
    main()
