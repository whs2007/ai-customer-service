"""应用配置（pydantic-settings，08 §10 环境变量规范）。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。环境变量优先，其次读取 backend/.env（已被 gitignore）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # 关闭复杂字段自动 JSON 解码，交由自定义校验器处理（兼容逗号分隔写法）
        enable_decoding=False,
    )

    # 应用基础信息
    app_name: str = "AI 智能客服系统"
    version: str = "0.1.0"
    debug: bool = False
    json_logs: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # 数据库 / 缓存（08 §10）
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ai_customer_service"
    redis_url: str = "redis://127.0.0.1:6379/0"
    skip_redis: bool = False  # 测试环境跳过 Redis 探测

    # JWT（08 §4.1 / §8）
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120  # access 2h
    refresh_token_expire_days: int = 7  # refresh 7d

    # CORS 白名单（08 §10）
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # 文件存储目录（08 §4.2 本地存储，规划 S3/MinIO）
    storage_dir: str = "storage"

    # 任务执行方式：inline（响应后进程内异步处理，默认，本机无 Redis 可用）
    #              celery（需要 Redis broker + worker，08 §3.4）
    task_backend: str = "inline"

    # Embedding 配置（08 §2/#2：bge-m3 1024 维；无 Key 时使用确定性 mock 向量，便于离线开发）
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_api_key: str = ""
    embedding_base_url: str = ""

    # 重排配置（08 §2/#15：密钥仅存 .env，不入代码库；B3 起使用）
    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_model: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json

                return json.loads(v)
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
