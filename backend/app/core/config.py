"""应用配置（pydantic-settings，08 §10 环境变量规范）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。环境变量优先，其次读取 backend/.env（已被 gitignore）。"""

    # 固定基于代码位置解析 .env：无论从仓库根还是 backend/ 下运行，都加载同一份配置
    _BACKEND_DIR = Path(__file__).resolve().parents[2]

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
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
    # 运行环境：development / test / production（生产环境强制校验密钥与凭据）
    environment: str = "development"

    # 数据库 / 缓存（08 §10）
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ai_customer_service"
    redis_url: str = "redis://127.0.0.1:6379/0"
    skip_redis: bool = False  # 测试环境跳过 Redis 探测
    # 连接池（08 §10：生产按并发调优；chat 流程已避免跨 LLM 调用持有连接）
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_connect_timeout: int = 10
    db_statement_timeout_ms: int = 30000

    # JWT（08 §4.1 / §8）：生产环境禁止使用默认值，启动时强校验
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "ai-customer-service"
    jwt_audience: str = "ai-customer-service-web"
    access_token_expire_minutes: int = 120  # access 2h
    refresh_token_expire_days: int = 7  # refresh 7d

    # 速率限制（08 §8：认证与 LLM 调用防滥用）
    rate_limit_enabled: bool = True
    login_rate_per_minute: int = 10
    refresh_rate_per_minute: int = 30
    chat_rate_per_minute: int = 120
    register_rate_per_minute: int = 5  # 用户端注册防刷（12 §2.1）
    login_failed_lock_threshold: int = 5  # 连续失败锁定阈值
    login_lock_minutes: int = 15  # 锁定时长

    # LLM 容错（08 §8：超时重试与降级）
    llm_max_retries: int = 2
    llm_retry_base_delay: float = 0.5

    # 初始管理员引导（替代迁移硬编码种子）
    admin_username: str = "admin"
    admin_initial_password: str = ""
    admin_display_name: str = "管理员"

    # CORS 白名单（08 §10）
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # 文件存储目录（08 §4.2 本地存储，规划 S3/MinIO）
    storage_dir: str = "storage"
    # 上传限制（与前端 nginx client_max_body_size 保持一致）
    max_upload_size_mb: int = 20
    allowed_extensions: list[str] = [
        ".xlsx", ".csv", ".md", ".txt", ".pdf", ".docx",
    ]

    # 任务执行方式：inline（响应后进程内异步处理，默认，本机无 Redis 可用）
    #              celery（需要 Redis broker + worker，08 §3.4）
    task_backend: str = "inline"
    # SSE 实时连接上限（P1-4：防单实例连接数失控；超出返回 429）
    sse_max_connections: int = 1000
    # 工单职责分离（默认关）：admin 默认只读工单（看板/列表/详情），
    # 不参与认领/回复/关闭/释放等一线操作；开启后 admin 可操作（写审计由路由统一处理）。
    allow_admin_ticket_ops: bool = False

    # Embedding 配置（08 §2/#2：bge-m3 1024 维；无 Key 时使用确定性 mock 向量，便于离线开发）
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    # RAG 检索命中阈值：相似度低于该值视为未命中，进入兜底（防止无关问题被硬答）
    retrieval_min_similarity: float = Field(default=0.70, ge=0.0, le=1.0)

    # LLM 配置（08 §2：智谱 GLM 起步；未配置 Key 时使用模板化 mock 生成，便于离线开发）
    llm_provider: str = "zhipu"
    llm_model: str = "glm-4-flash"
    llm_api_key: str = ""
    llm_base_url: str = ""

    # 重排配置（08 §2/#15：密钥仅存 .env，不入代码库；B3 起使用）
    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_model: str = ""

    # 安全加固（08 §8，B6b）
    scan_enabled: bool = False  # 恶意文件扫描（可插拔，默认关闭；接入点见 pipeline/scanner.py）
    moderation_enabled: bool = True  # 内容审核（本地敏感词兜底；配置 API 后优先外部审核）
    moderation_api_url: str = ""
    moderation_api_key: str = ""

    # 可观测（08 §9，B6b）
    metrics_enabled: bool = True  # Prometheus 指标 /metrics
    metrics_token: str = ""  # Prometheus 抓取专用 token（admin JWT 之外的可选通道）
    log_retention_days: int = 30  # 日志保留策略（天），清理任务后续实现

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip().lower() for item in v.split(",") if item.strip()]
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        env = (v or "development").strip().lower()
        if env not in ("development", "test", "production"):
            raise ValueError(f"ENVIRONMENT 取值不合法：{v}（支持 development/test/production）")
        return env

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str, info: Any) -> str:
        """生产环境拒绝空值/占位符：避免使用公开默认密钥签发可伪造的 JWT。"""
        env = (info.data.get("environment") or "development").lower()
        secret = (v or "").strip()
        if env == "production" and (not secret or secret == "change-me-in-production"):
            raise ValueError(
                "生产环境必须设置强随机 JWT_SECRET，例如："
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return secret

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
