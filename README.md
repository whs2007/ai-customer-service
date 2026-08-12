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
| B4.5 评测 / B5 工单与统计 | ⏳ | 应用评测、工单列表、会话记录详情、看板（待实施） |
| M1 前端框架 | ✅ | 9 菜单布局、路由、设计令牌、登录 |

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
copy .env.example .env                            # 填写 DATABASE_URL 等真实值
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

默认管理员（仅本地开发）：`admin / admin123`。测试：`pytest -q`。

### 前端

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173，/api 代理到 127.0.0.1:8000
```

## 安全约定

- 所有密钥（RERANK_API_KEY、EMBEDDING_API_KEY、JWT_SECRET、数据库口令）只放 `.env`（已 gitignore），严禁写入代码、文档或日志。
- 知识库文档为业务敏感数据：按知识库隔离权限、日志脱敏（规划）。
