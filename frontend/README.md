# AI 智能客服系统 · 前端（M1 骨架）

## 技术栈

- Vite + React 18 + TypeScript
- Ant Design 5（设计令牌按需求文档 01 §4 落地）
- React Router 6（路由按 01 §3 / 00 §4.3）
- Zustand（认证状态）+ TanStack Query（服务端状态）
- axios（统一响应解包 `{code, message, data}`，08 §6.1）

## 本地运行

```bash
npm install
npm run dev
```

开发服务器默认 `http://localhost:5173`，`/api` 已代理到 `http://127.0.0.1:8000`。

## 账号

默认管理员（本地开发种子，见后端 README）：`admin / admin123`。

## 目录说明

- `src/layouts/`：全站“左侧导航 + 右侧内容区”布局与路由守卫
- `src/pages/`：9 个一级菜单占位页 + 登录页
- `src/theme/tokens.ts`：设计令牌（01 §4 色彩/字体/圆角/阴影）
- `src/api/`：axios 封装（token 注入、401 刷新、统一响应）
- `src/stores/auth.ts`：认证状态（zustand + persist）
- `src/pages/knowledge/`：B2 知识库三页面（列表/创建、文档列表、Chunk 管理）
- `src/pages/RecallTest.tsx`：B3 检索测试页（多库/标签/模式/TopK、召回卡片、重排前后对比、示例问题）

## 里程碑对应

工作台/工单/评测/会话记录 → M5；检索 → M3；对话 → M4；知识库 → M2；
设置/帮助 → M6。占位页不实现业务 UI。
