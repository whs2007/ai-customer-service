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

## B4 智能应答交付范围

- LangGraph 对话图：意图路由（订单/物流 → 工具 mock、政策 → RAG、投诉 → 转人工、其他 → 兜底升级）
- `POST /api/chat` SSE 流式：message_start / token / citations / done / error（+ form 事件）
- 转人工建单（TK+时间戳+随机），会话置 transferred；引用反馈 `POST /api/feedbacks`
- 会话/消息/trace_logs 落库，`GET /api/sessions`、`GET /api/sessions/{id}` 恢复会话
- 意图规则可配置（`/api/settings/intent`）；模型配置列表/默认切换（admin）
- LLM 客户端：配置 `LLM_API_KEY` 走 OpenAI 兼容流式；未配置用 mock 生成

SSE 示例：

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"kb_ids":["<kb_id>"],"message":"商品签收后几天可以退货？"}'
```

## B4.5 应用评测交付范围

- `/api/evaluations/*`：评测集 CRUD、样本导入（逐条/JSON 批量/30 条公开样例）、评测任务（异步执行 + 进度/报告/重试）、人工调通过、回流候选确认/拒绝
- 执行链路：逐条走 LangGraph 对话图（eval_mode 不建单）→ LLM-as-judge 打分（有 Key 走真实模型，无 Key 用确定性启发式）
- 回流：引用反馈 `include_in_eval=true` → 候选 → 管理员确认入集

## B5 运营闭环交付范围

- 工单：`/api/tickets` 列表筛选/详情（命中片段+时间线）/状态流转 open→processing→closed（ticket_notes + 审计）
- 工作台：`/api/dashboard/stats|trend|intents`（02 §7 口径，按需计算 + 30s 进程内缓存 + dashboard_stats 落表）
- 会话记录：`/api/sessions` 列表筛选（时间/意图/状态/转人工/关键词/标注）+ 详情（trace/工单/标注）+ `/annotations` 标注回流评测候选

## B6a 系统设置交付范围

- 模型配置：CRUD/测试连通/按用途默认切换（对话/Embedding/重排），API Key 加密存储 + 脱敏
- 配置接口：`/api/settings/prompt|escalation|chunking`（对话链路与分块参数运行时读取）
- 用户管理：`POST/PUT /api/auth/users`、`PUT /api/auth/users/{id}/password`；知识库可见性（all/role/user）
- 审计：`GET /api/audit-logs`；数据管理：`POST /api/admin/rebuild-vectors`、`GET /api/admin/export`
