# AI 智能客服系统

面向企业管理者的 Web 端 AI 客服工作台，覆盖“知识管理 → 检索测试 → 智能应答 → 工单流转 → 数据看板”全链路，技术栈为 **LangGraph + RAG**（管理端；用户端本期不做）。

> 需求基线：`需求文档/`（00–10 模块文档）+ `需求功能报告.md`（主文档，含实施记录与【新增】【变更】【建议】标注）；原型见 `prototype/`。

## 技术栈

| 层面 | 选型 |
| --- | --- |
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy 2.0（async）/ Alembic / PostgreSQL 15+（pgvector）/ Redis / Celery / structlog |
| 前端 | Vite / React 18 / TypeScript / Ant Design 5 / Zustand / TanStack Query |
| AI | 智谱 GLM（LLM）、bge-m3（Embedding，1024 维）、SiliconFlow bge-reranker-v2-m3（重排） |

## 目录结构

```
├─ backend/          # FastAPI 后端（B1 基建 / B2 知识库 / B3 检索验证）
├─ frontend/         # React 管理端（M1 框架 / 知识库页面 / 检索测试页）
├─ 需求文档/          # 按模块拆分的需求文档（00–10）
├─ prototype/        # 原型截图与 HTML 原型
└─ 需求功能报告.md     # 需求主文档（v1.1 + 实施记录）
```

## 模块进度

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| B1 基建 | ✅ | 项目骨架、JWT + RBAC、统一响应/错误码、日志、/health |
| B2 知识库 | ✅ | KB CRUD、上传解析（xlsx/csv/md/txt/pdf/docx）、Chunk 管理、向量化 |
| B3 检索验证 | ✅ | pgvector 余弦 + tsvector 全文 RRF 融合、SiliconFlow 重排、多库权限 |
| B4 智能应答 | ✅ | LangGraph 对话、SSE 流式、引用反馈、转人工、会话恢复 |
| B4.5 评测闭环 | ✅ | 评测集/任务/报告、30 条公开样例、回流候选 |
| B5 运营闭环 | ✅ | 工单流转与时间线、工作台 KPI/趋势/意图、会话记录与标注回流 |
| B6a 系统设置与帮助 | ✅ | 六 Tab 设置、用户与知识库权限、日志审计、数据管理、帮助文档 |
| B6b 部署与安全加固 | ✅ | docker compose 全栈、Celery、Fernet 密钥、上传嗅探、内容审核、Prometheus 指标 |
| M1 前端框架 | ✅ | 9 菜单布局、路由、设计令牌、登录 |
| 用户端（11–12） | ✅ | 自助注册/登录锁定、在线咨询（SSE 流式）、我的工单与评价、个人中心 |
| 客服工作台（13） | ✅ | 三栏队列/对话/工单信息、原子认领、回复/关闭、在线状态、SSE 实时联动 |
| 三端实时联动（11 §9） | ✅ | SSE 事件总线（进程内 + Redis pub/sub 中继）、未读游标、管理端工单看板与渠道配置 |

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
copy .env.example .env                            # 填写 DATABASE_URL/JWT_SECRET 等真实值
alembic upgrade head
python -m app.cli bootstrap                       # 引导初始管理员（见下方说明）
uvicorn app.main:app --reload --port 8000
```

**初始管理员说明**：迁移不再硬编码 admin/admin123。首次部署请设置
`ADMIN_INITIAL_PASSWORD` 后执行 `python -m app.cli bootstrap`；开发环境未设置该变量时
会创建 `admin/admin123` 并输出告警（仅限本地）。测试：`pytest -q`。

> 安全提示：`ENVIRONMENT=production` 时应用会拒绝使用默认 `JWT_SECRET`（启动即报错）。
> 生产部署请通过 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成强随机密钥。
>
> 运行参数（连接池、JWT 签发方、上传大小、指标 token、测试库等）见 `backend/.env.example`；
> 测试建议设置 `TEST_DATABASE_URL` 指向独立测试库，避免污染开发数据。

### 前端

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173，/api 代理到 127.0.0.1:8000
```

## 安全约定

- 所有密钥（RERANK_API_KEY、EMBEDDING_API_KEY、JWT_SECRET、数据库口令）只放 `.env`（已 gitignore），严禁写入代码、文档或日志。
- 知识库文档为业务敏感数据：按知识库隔离权限、日志脱敏（规划）。
- docker compose 默认 `ENVIRONMENT=production`：需在 `.env` 设置 `POSTGRES_PASSWORD`、
  `REDIS_PASSWORD`、`JWT_SECRET`、`GRAFANA_ADMIN_PASSWORD`，并建议设置 `ADMIN_INITIAL_PASSWORD`
  （migrate 服务会自动引导管理员）与 `METRICS_TOKEN`（Prometheus 抓取 /metrics 使用）。
  compose 额外提供 beat（定时清理）、prometheus/grafana（指标采集与看板）、backup（每日 pg_dump）服务。
