# AGENTS.md

## 项目定位
YuanVerdict（代号 VerdictAI-Now）：研发评审垂类 AI 决策 Agent 平台——录音转写、Multi-Agent 提取纪要/行动项/风险/决策、决策入库向量化、AI 对话双路 RAG 流式回答。

## 怎么跑起来
- 前置：Python 3.11+、Node 18+、Docker、pnpm
- 基础设施：`docker compose up -d`（PostgreSQL 宿主端口 **15432**、Redis 6379）
- 后端：`cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8787`（需先 `pip install -r requirements.txt`，`cp .env.example .env`，`alembic upgrade head`）
- 前端：`cd frontend && pnpm install && pnpm run dev`（5173，/api 代理到 8787）
- 一键脚本：根目录 `dev.ps1` / `dev.cmd`（单终端，自动起 Docker + 迁移 + seed + 双端后台）

## 技术栈
- 后端：FastAPI + SQLAlchemy 2 async + Alembic + PostgreSQL 16/pgvector + Redis
- AI：LangGraph v2（Planner 动态 fan-out + Harness 约束）+ 通义千问 qwen-plus + text-embedding-v3（1024 维）+ DashScope paraformer-v2 ASR
- 前端：React 19 + Vite 8 + TypeScript + TanStack Query + Zustand + Tailwind 4 + @tanstack/react-virtual

## 目录与约定
- `backend/app/api` 路由 / `services` 业务（转写/决策/知识/对话）/ `agents` LangGraph 编排（`harness` 约束、`nodes` 节点）/ `models` ORM / `schemas` Pydantic / `db` 连接
- 决策领域独立三表：`decisions` / `decision_options` / `decision_relations`（pgvector + 写入时关联 top-3）
- `frontend/src/features` 功能页（meetings/summaries/decisions/chat/knowledge/agent-runs）
- 转写三态：`TRANSCRIPTION_PROVIDER=auto/mock/dashscope`，默认 `auto`（真实转写不可用时降级 Mock）
- Harness 约束：`harness_wrap` 装饰器 + contextvar 传递 run_id/budget，不污染 LangGraph state

## 当前状态与下一步
- MVP 主链路已实现；DB 宿主端口为 15432；前端仍声明未使用的 `@microsoft/fetch-event-source` 依赖，待清理
- 学习文档在 `VerdictAI-Now/docs/lark-work/`（独立 docs git 仓库内，不在本代码仓库）多文件树（README_nav + 01~06 章 + 02_problems/），由 `sync_feishu.ps1` 幂等推送飞书；`YuanVerdict_learning_doc.md` 为拆分前旧单文件留档不推送
- 待办：完整"暂停 + 人工审批恢复"未落地（MVP 直接放行）；`sfu/` 与 `rooms` 为未启用 MVP

<!-- CODEGRAPH_START -->
## YuanVerdict CodeGraph scope

`YuanVerdict/` is the Git repository and CodeGraph project root. It is located
inside the larger `VerdictAI-Now/` workspace, whose outer directory is not a
Git repository and does not contain a `.codegraph/` directory.

For all code under this project, apply the global CodeGraph rules with
`YuanVerdict/` as the repository root:

- When calling `codegraph_explore` via MCP, set `projectPath` to the absolute
  path of the `YuanVerdict/` directory.
- When using CodeGraph from the shell, run commands from inside `YuanVerdict/`.
- The absence of `.codegraph/` from the outer `VerdictAI-Now/` directory must
  not be used as a reason to skip CodeGraph.
<!-- CODEGRAPH_END -->
