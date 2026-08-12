# AI 智能客服系统 · 后端（B1 基建骨架）

## 技术栈（08 §2）

- Python 3.11+ / FastAPI + Uvicorn
- SQLAlchemy 2.0（async）+ Alembic + PostgreSQL 15+（pgvector 已确认）
- Redis（B1 可选：不可用时降级为告警，不影响启动；B2 起 Celery 依赖）
- JWT（access 2h + refresh 7d，轮换）+ RBAC（admin/agent/viewer）
- structlog 结构化日志（JSON 或控制台）
- pytest + httpx 冒烟测试

## 快速开始

### 1. 准备数据库

需要 PostgreSQL 15+ 且已安装 pgvector 扩展（08 §2/#3）。本机已安装 pgvector 0.8.6（PostgreSQL 18）。

无本机 PG/Redis 时可用 `docker-compose up -d` 启动基础设施（postgres + pgvector + redis）。

### 2. 配置

```bash
copy .env.example .env   # Windows
```

编辑 `.env` 中的 `DATABASE_URL` 等真实值。**密钥（如 RERANK_API_KEY）只放 .env，不入代码库**。

### 3. 安装依赖与迁移

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
```

迁移会自动：创建 pgvector 扩展、`users`/`audit_logs` 表、种子默认管理员。

### 4. 启动

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档（debug 模式）：http://127.0.0.1:8000/docs
- 健康检查：`GET /health`
- 登录：`POST /api/auth/login`
- 当前用户：`GET /api/auth/me`

### 5. 测试

```bash
pytest -q
```

测试自动使用独立数据库 `ai_customer_service_test`（读取 `.env` 的 DATABASE_URL 推导），并执行迁移。

## 默认账号（仅本地开发）

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| admin | admin123 | admin |

生产环境不得使用种子账号，应由初始化流程创建并修改密码。

## 目录结构（08 §3.4）

```
backend/
├─ app/
│  ├─ main.py              # FastAPI 入口（应用工厂、异常处理、请求日志）
│  ├─ api/                 # 路由与依赖注入（deps.py：RBAC）
│  ├─ core/                # config / security / logging / exceptions / response / redis
│  ├─ models/              # SQLAlchemy 模型（users、audit_logs）
│  ├─ schemas/             # Pydantic 请求/响应
│  ├─ services/            # 业务逻辑（auth_service）
│  └─ db/                  # 异步引擎与会话
├─ alembic/                # 迁移（含 pgvector 扩展）
├─ tests/                  # pytest 冒烟测试
└─ pyproject.toml
```

## B1 交付范围

- 统一响应 `{code, message, data}` 与错误码（08 §7）
- JWT 登录 / 刷新 / /me + RBAC（admin 可访问用户列表演示）
- 登录审计（audit_logs）
- Redis 连接骨架（`core/redis.py`，优雅降级）
- structlog 结构化日志 + request_id
- /health（应用/数据库/Redis 状态）
- pytest 冒烟测试 10 项

## B2 知识库交付范围

- 知识库 CRUD（名称唯一 409、软删除 + 级联清空文档/切片、审计）
- 文档上传（multipart，扩展名白名单 + 20MB）、解析（xlsx/csv FAQ 模板；md/txt/pdf/docx 500/50 分块）、状态机（uploading → parsing → embedding → completed/failed）、失败重新解析
- Chunk 管理（列表/新增/编辑/删除，编辑后单条重新向量化）
- pgvector 向量化（bge-m3 1024 维 + HNSW 索引；`EMBEDDING_API_KEY` 为空时使用 mock 向量，仅限开发）
- 异步任务：默认 `TASK_BACKEND=inline`（无 Redis 也可跑通）；`TASK_BACKEND=celery` 需 Redis + worker

### 知识库接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge-bases` | 知识库列表（含文档数） |
| POST | `/api/knowledge-bases` | 创建知识库（admin） |
| PUT/DELETE | `/api/knowledge-bases/{id}` | 更新 / 软删除（admin） |
| GET | `/api/knowledge-bases/{id}/documents` | 文档列表（keyword/分页） |
| POST | `/api/knowledge-bases/{id}/documents` | 上传文档（admin，multipart） |
| GET/DELETE | `/api/documents/{id}` | 文档详情 / 删除（admin） |
| POST | `/api/documents/{id}/reparse` | 重新解析（admin） |
| GET | `/api/documents/{id}/chunks` | Chunk 列表 |
| POST | `/api/chunks` | 新增 Chunk（admin） |
| PUT/DELETE | `/api/chunks/{id}` | 编辑 / 删除 Chunk（admin） |

样例文件：`samples/FAQ知识库导入模板.xlsx`（可用 `python scripts/make_sample_xlsx.py` 重新生成）。

## B3 检索验证交付范围

- `POST /api/retrieval/test`：多知识库 + 标签过滤 + TopK（1–10）+ 检索方式（vector / hybrid / hybrid_rerank）
- 向量检索：pgvector 余弦；关键词检索：tsvector 生成列 + GIN 索引（中文 bigram 查询）；RRF 融合 + 检索分 0–100 归一化
- 重排：SiliconFlow `/rerank`（`BAAI/bge-reranker-v2-m3`），输入"问题+答案"，无 Key 自动降级并标注 `actual_mode`
- 权限：admin/agent 可检索，viewer 403；多库逐库校验，无效库剔除

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/retrieval/test \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"kb_ids":["<kb_id>"],"query":"商品签收后几天可以退货？","top_k":3,"retriever_mode":"hybrid_rerank"}'
```
