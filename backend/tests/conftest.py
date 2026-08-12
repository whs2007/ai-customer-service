"""pytest 全局夹具：测试数据库准备 + 应用/客户端工厂。

说明：建库与 Alembic 迁移通过子进程执行（独立进程无事件循环冲突，
不受 pytest-asyncio 循环作用域影响）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator, Callable
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

_TEST_DB_NAME = "ai_customer_service_test"
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """最小 .env 读取：仅当环境变量未设置时注入（凭据只存 .env，不入测试代码）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(_BACKEND_DIR / ".env")

# 必须在导入 app 之前覆盖配置：使用独立测试库 + 跳过 Redis
_BASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not _BASE_URL:
    raise RuntimeError("缺少 DATABASE_URL / TEST_DATABASE_URL（请在 backend/.env 中配置）")
if "/ai_customer_service" in _BASE_URL:
    _TEST_URL = _BASE_URL.replace("/ai_customer_service", f"/{_TEST_DB_NAME}", 1)
else:
    _TEST_URL = _BASE_URL
os.environ["DATABASE_URL"] = _TEST_URL
os.environ["SKIP_REDIS"] = "1"
os.environ["DEBUG"] = "false"

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402


def _run_python_subprocess(script: str) -> None:
    """在子进程中执行 Python 代码（cwd=backend，环境沿用当前进程）。"""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"子进程执行失败:\n{result.stdout}\n{result.stderr}")


def _ensure_database_exists() -> None:
    """若测试库不存在则创建（通过 postgres 库连接）。"""
    script = f"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

admin_url = {_TEST_URL!r}.rsplit("/", 1)[0] + "/postgres"
db_name = {_TEST_DB_NAME!r}

async def main():
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {{"name": db_name}},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{{db_name}}"'))
    await engine.dispose()

asyncio.run(main())
"""
    _run_python_subprocess(script)


def _run_migrations() -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = _TEST_URL
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic 迁移失败:\n{result.stdout}\n{result.stderr}")


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    """会话级：确保测试库存在并迁移到 head（子进程执行）。"""
    _ensure_database_exists()
    _run_migrations()
    yield


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_session():
    async with get_session_factory()() as session:
        yield session


@pytest.fixture
async def create_user() -> Callable[..., None]:
    """测试辅助：直接写库创建用户。"""
    from app.core.security import hash_password
    from app.models.user import User

    async def _create(
        username: str,
        password: str,
        display_name: str,
        role: str,
    ) -> None:
        async with get_session_factory()() as session:
            session.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    display_name=display_name,
                    role=role,
                )
            )
            await session.commit()

    return _create


@pytest.fixture
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    """管理员登录请求头。"""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def user_headers(client: AsyncClient, create_user) -> Callable[..., dict[str, str]]:
    """按角色创建用户并返回登录请求头。"""

    async def _make(role: str) -> dict[str, str]:
        username = f"{role}_{uuid.uuid4().hex[:8]}"
        await create_user(username, "test12345", role, role)
        resp = await client.post(
            "/api/auth/login",
            json={"username": username, "password": "test12345"},
        )
        token = resp.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make
