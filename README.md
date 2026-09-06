# 研发评审智能决策平台

> 面向研发评审场景的 **离线会议决策提取与检索平台**。上传评审录音 → 转写 → Multi-Agent 并行提取纪要/行动项/风险/决策 → 决策入库向量化 → AI 对话双路 RAG 召回。

GitHub 仓库：[`a446628089/DdddkVerdict`](https://github.com/a446628089/DdddkVerdict)。代码与本地配置沿用 YuanVerdict / Yuan-Meet 命名。

首次公开导入按功能里程碑整理为 20 次提交，提交时间为整理时间。

---

## 核心能力

### 离线会议处理链路

```
音频上传 → TranscriptionService（DashScope ASR / Mock 降级）
         → 存储 Transcript（含说话人 + 时间戳）
         → Multi-Agent 并行（LangGraph）
            ├─ 摘要 Agent        → Summary
            ├─ 行动项 Agent      → ActionItem[]
            ├─ 风险 Agent        → Risk[]
            └─ 决策抽取 Agent    → Decision[]（两步流水线）
         → 落库 + 决策向量化 + 即时关联 top-3 历史决策
```

### 决策抽取两步流水线

| 步骤 | 节点 | 职责 |
|------|------|------|
| Step 1 | `DecisionDetector` | LLM 全量扫描转写文本，定位决策段（区分 决策/提议/推迟），`confidence ≥ 0.7` 过滤 |
| Step 2 | `OptionExtractor` | 对每个决策段结构化抽取：标题 / 背景 / 候选方案（含 pros/cons）/ 已选方案 / 理由 / 反对意见 / 决策人 |

### Harness 约束框架

每个 Agent 节点由 `harness_wrap` 包裹，提供：

- **BudgetGuard** — Token / 成本预算，超限抛 `BudgetExceededError`
- **CircuitBreaker** — 连续失败熔断
- **RetryPolicy** — 可配置重试次数与退避
- **OutputValidator** — 结构化校验 + 回灌重试
- **AgentRun** — 节点耗时 / Token / 成本 / Tool 调用全生命周期记录

ContextVar 跨节点传递 `run_id` / `budget_guard`，不侵入 LangGraph state。

### 双路 RAG 召回

AI 对话检索时依次召回两路结果（当前实现为串行调用），再用 RRF 融合后送入 LLM：

```
用户提问
  → 文档路：knowledge_service.search()（纪要 + 知识文档，向量 + 全文 + RRF）
  → 决策路：decision_graph_service.search()（决策库 pgvector 语义检索）
  → RRF 融合（k=60）→ top-5 上下文
  → LLM 流式输出（SSE）
```

---

## 技术栈

### 后端

| 领域 | 技术 |
|---|---|
| Web 框架 | FastAPI 0.115 + Uvicorn |
| 数据库 | PostgreSQL 16 + pgvector（cosine, ivfflat, 1024 维） |
| ORM | SQLAlchemy 2.0（async）+ Alembic |
| 缓存 | Redis 7 |
| Agent 编排 | LangGraph 0.2（StateGraph + 条件路由 + 并行 fan-out） |
| LLM | 通义千问 qwen-plus（兼容 OpenAI 接口） |
| Embedding | text-embedding-v3（1024 维） |
| ASR | DashScope Paraformer-v2（录音文件识别，OSS 中转） |
| 文档解析 | pypdf / python-docx |

### 前端

| 领域 | 技术 |
|---|---|
| 框架 | React 19 + TypeScript |
| 构建 | Vite 8 |
| 服务端状态 | TanStack Query 5 |
| UI 状态 | Zustand 5 |
| 路由 | React Router 7（懒加载） |
| 样式 | Tailwind CSS 4 |
| Markdown | react-markdown + remark-gfm + rehype-highlight |
| 流式通信 | 原生 fetch + ReadableStream.getReader() 解析 SSE |
| 虚拟滚动 | @tanstack/react-virtual |

### 基础设施

| 领域 | 技术 |
|---|---|
| 容器化 | Docker Compose（PostgreSQL + pgvector + Redis） |
| 向量数据库 | pgvector（PostgreSQL 扩展） |

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                           前端（React）                           │
│  会议管理 │ 纪要详情 │ 决策库 │ AI 对话 │ 知识库 │ Agent 监控     │
└──────────────┬───────────────────────────────────┬───────────────┘
               │ HTTP / SSE                         │
┌──────────────▼───────────────────────────────────▼───────────────┐
│                        后端（FastAPI）                            │
├───────────┬───────────┬───────────┬───────────┬──────────────────┤
│ meetings  │ summaries │ decisions │   chat    │  agent_runs API  │
├───────────┴───────────┴───────────┴───────────┴──────────────────┤
│                         Service Layer                             │
│  MeetingService │ TranscriptionService（ASR + Mock 降级）         │
│  SummaryService │ DecisionGraphService │ ChatService              │
│  KnowledgeService（向量 + 全文 + RRF）│ EmbeddingService          │
├──────────────────────────────────────────────────────────────────┤
│                  Multi-Agent（LangGraph v2）                      │
│  [planner] → [budget_check] → fan-out（动态路由）                 │
│    ├─ summary_agent      ┐                                        │
│    ├─ action_items_agent │ 并行（套 Harness）                     │
│    ├─ risks_agent        │                                        │
│    └─ decision_extractor ┘                                        │
│  → [output_validator] → [human_review] → [persist]               │
├──────────────────────────────────────────────────────────────────┤
│                    决策抽取两步流水线                              │
│  DecisionDetector（全量扫描定位）→ OptionExtractor（结构化抽取）  │
├──────────────────────────────────────────────────────────────────┤
│                    双路 RAG 召回（AI 对话）                       │
│  文档路（knowledge_service）+ 决策路（decision_graph_service）     │
│  → RRF 融合 → top-5 上下文 → LLM 流式输出                         │
└──────────────┬───────────────────────────────────┬───────────────┘
               │                                    │
┌──────────────▼──────────────────┐ ┌──────────────▼───────────────┐
│   PostgreSQL + pgvector         │ │           Redis              │
│ meetings / transcripts /        │ │                               │
│ summaries / action_items /      │ │                               │
│ risks / decisions /             │ │                               │
│ decision_options /              │ │                               │
│ decision_relations /            │ │                               │
│ knowledge_documents /           │ │                               │
│ agent_runs / chat_sessions      │ │                               │
└─────────────────────────────────┘ └──────────────────────────────┘
```

> 当前 `human_review` 是审批预留节点，MVP 阶段直接放行；`persist` 只标记图执行完成，实际落库由 `SummaryService` 统一处理。

---

## 项目结构

```
yuan-meet/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── harness/              # Harness 约束框架
│   │   │   │   ├── budget.py         # BudgetGuard（Token/成本预算）
│   │   │   │   ├── circuit_breaker.py# CircuitBreaker（熔断）
│   │   │   │   ├── retry.py          # RetryPolicy（重试退避）
│   │   │   │   ├── validator.py      # OutputValidator（结构校验）
│   │   │   │   └── wrap.py           # harness_wrap 装饰器 + ContextVar
│   │   │   ├── nodes/
│   │   │   │   ├── planner.py        # Planner（会议类型识别 + 动态调度）
│   │   │   │   ├── budget_check.py   # 文本压缩 + 预算预检
│   │   │   │   ├── decision_detector.py  # Step 1：决策段定位
│   │   │   │   ├── option_extractor.py   # Step 2：结构化选项抽取
│   │   │   │   ├── decision_extractor.py # 两步流水线组合节点
│   │   │   │   ├── output_validator.py   # 校验 + 回灌重试
│   │   │   │   └── human_review.py       # 审批预留节点（MVP 直接放行）
│   │   │   ├── tools/                # Tool Registry（Agent 工具调用）
│   │   │   ├── meeting_graph.py      # v1 基础图（保留对照）
│   │   │   └── meeting_graph_v2.py   # v2 Harness 版（四路并行）
│   │   ├── api/
│   │   │   ├── meetings.py           # 会议 CRUD + 音频上传
│   │   │   ├── summaries.py          # 纪要生成 + 行动项 + 风险
│   │   │   ├── decisions.py          # 决策库（列表/详情/搜索）
│   │   │   ├── chat.py               # AI 对话（SSE 流式）
│   │   │   ├── knowledge.py          # 知识库检索 + 文档管理
│   │   │   ├── agent_runs.py         # Agent 运行监控 + 审批
│   │   │   └── rooms.py              # 实时房间（MVP 未启用）
│   │   ├── services/
│   │   │   ├── transcription_service.py  # 转写（DashScope + Mock 降级）
│   │   │   ├── dashscope_asr_service.py  # DashScope 原生 ASR
│   │   │   ├── oss_service.py            # 阿里云 OSS（音频中转）
│   │   │   ├── summary_service.py         # Agent 工作流协调 + 落库
│   │   │   ├── decision_graph_service.py  # 决策入库 + 向量关联 + 检索
│   │   │   ├── chat_service.py            # AI 对话（双路 RAG + RRF）
│   │   │   ├── knowledge_service.py       # 知识检索（向量 + 全文 + RRF）
│   │   │   ├── embedding_service.py       # 文本向量化
│   │   │   ├── agent_run_service.py       # AgentRun 生命周期
│   │   │   ├── document_parser.py         # 文档解析（PDF/DOCX）
│   │   │   └── document_chunker.py        # 文档分块
│   │   ├── models/
│   │   │   ├── decision.py           # Decision / DecisionOption / DecisionRelation
│   │   │   ├── agent_run.py          # AgentRun（含 steps / node_usage）
│   │   │   ├── meeting.py / transcript.py / summary.py
│   │   │   ├── action_item.py / risk.py
│   │   │   ├── knowledge_doc.py / chat.py
│   │   │   └── room.py / realtime_session.py（MVP 未启用）
│   │   ├── schemas/                  # Pydantic 响应模型
│   │   ├── db/                       # 数据库连接
│   │   └── config.py                 # 配置管理
│   ├── alembic/versions/             # 数据库迁移
│   ├── scripts/                      # 测试脚本
│   ├── seed_data.py                  # 示例数据
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── features/
│       │   ├── meetings/             # 会议管理（列表/详情/音频上传/转写）
│       │   ├── summaries/            # 纪要（列表/详情/行动项/风险）
│       │   ├── decisions/            # 决策库（列表/详情/语义搜索/分页）
│       │   ├── chat/                 # AI 对话（流式 + 虚拟滚动）
│       │   ├── knowledge/            # 知识库（上传/检索/管理）
│       │   └── agent-runs/           # Agent 监控（统计/步骤/审批）
│       ├── components/
│       │   ├── layout/               # AppLayout / Sidebar / Header
│       │   └── ui/                   # Button / Card / Badge / Markdown 等
│       ├── api/                      # ky HTTP 客户端
│       ├── hooks/                    # 虚拟列表 / 语音
│       ├── lib/                      # constants / utils / query-client
│       ├── router/                   # 路由配置（懒加载）
│       └── types/                    # TypeScript 类型定义
├── sfu/                              # mediasoup SFU（MVP 未启用）
├── docker-compose.yml                # PostgreSQL + pgvector + Redis
└── README.md
```

---

## 数据模型

### 决策三表（核心）

```
decisions
├─ id (UUID, PK)
├─ meeting_id (FK → meetings)
├─ title (varchar 50)
├─ context / snippet (text)
├─ chosen_option (varchar 30)
├─ reasons / decided_by / objections (JSONB)
├─ decided_at / confidence
├─ embedding (vector(1024), ivfflat cosine)
└─ created_at

decision_options
├─ id (UUID, PK)
├─ decision_id (FK → decisions, CASCADE)
├─ name / pros / cons / proposed_by
└─ is_chosen (bool)

decision_relations
├─ source_decision_id (FK → decisions)
├─ target_decision_id (FK → decisions)
├─ relation_type (default 'relates')
├─ similarity_score (float)
└─ UNIQUE(source, target)
```

### 其他核心表

`meetings` / `transcripts` / `summaries` / `action_items` / `risks` / `knowledge_documents` / `agent_runs` / `chat_sessions` / `chat_messages`

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 22.12+（Vite 8 要求 Node.js 20.19+ 或 22.12+）
- pnpm 10.20.0（与 `frontend/package.json` 一致）
- Docker（用于 PostgreSQL + Redis）

### 获取项目

```bash
git clone https://github.com/a446628089/DdddkVerdict.git
cd DdddkVerdict
```

Windows 可在配置 `backend/.env` 并安装双端依赖后使用根目录 `dev.cmd` 启动、`stop.cmd` 停止。以下手动步骤中的 `source`、`cp` 和环境变量前缀适用于 Bash；PowerShell 可直接使用 `.venv\Scripts\python.exe` 执行 Python 模块。

### 1. 启动基础设施

```bash
docker compose up -d
```

### 2. 后端启动

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（通义千问 DashScope）

# 数据库迁移
PYTHONPATH=. alembic upgrade head

# 灌入示例数据（可选）
python seed_data.py

# 启动服务
uvicorn app.main:app --reload --port 8787
```

### 3. 前端启动

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

### 4. 访问应用

- 前端：http://localhost:5173
- API 文档：http://localhost:8787/docs

---

## 配置说明

编辑 `backend/.env`：

```bash
# 数据库（宿主端口 15432，与 docker-compose.yml 映射一致）
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:15432/yuan_meet

# LLM（通义千问，兼容 OpenAI 接口）
OPENAI_API_KEY=your-dashscope-api-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIMENSIONS=1024

# 音频转写
# auto: 优先真实转写，未配置 OSS 时自动降级 Mock（默认）
# mock: 仅 Mock（零配置本地开发）
# dashscope: 仅真实转写
TRANSCRIPTION_PROVIDER=auto

# 阿里云 OSS（真实转写需要，留空自动降级 Mock）
# OSS_ACCESS_KEY_ID=
# OSS_ACCESS_KEY_SECRET=
# OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
# OSS_BUCKET_NAME=
```

**Mock 转写体验**：完成依赖安装、数据库迁移并填入 `OPENAI_API_KEY` 后，可使用 Mock 转写体验主流程。纪要、决策抽取和 RAG 仍需可用的模型与向量服务。

**真实音频转写**：额外配置 4 个 OSS 环境变量，音频上传 OSS → 提交 DashScope ASR 任务 → 轮询解析（含说话人 + 时间戳）→ 清理 OSS。

---

## API 概览

| 模块 | 端点 | 说明 |
|------|------|------|
| 会议 | `POST /api/meetings` | 创建会议 |
| | `POST /api/meetings/{id}/upload` | 上传音频并加入后台转写任务 |
| 纪要 | `POST /api/meetings/{id}/summarize` | 触发 Multi-Agent |
| | `GET /api/meetings/{id}/summary` | 获取纪要 + 行动项 + 风险 |
| 决策 | `GET /api/decisions` | 决策列表（分页 + 按会议筛选） |
| | `GET /api/decisions/search?q=` | 语义搜索 |
| | `GET /api/decisions/{id}` | 决策详情（含 options + 关联决策） |
| 对话 | `POST /api/chat/sessions` | 创建会话 |
| | `POST /api/chat/sessions/{id}/stream` | 流式对话（SSE） |
| Agent | `GET /api/agent-runs` | 运行列表 |
| | `GET /api/agent-runs/{id}` | 运行详情（steps + budget） |
| | `POST /api/agent-runs/{id}/review` | 审批（approve/reject） |
| 知识 | `GET /api/knowledge/search?q=` | 知识检索 |
| | `POST /api/knowledge/documents` | 上传文档 |

完整文档：http://localhost:8787/docs

---

## 前端页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 会议列表 | 会议管理入口 |
| `/meetings/:id` | 会议详情 | 音频上传 + 转写 + 触发纪要 |
| `/summaries` | 纪要列表 | 所有会议纪要 |
| `/summaries/:id` | 纪要详情 | 纪要 + 行动项 + 风险（Markdown 渲染） |
| `/decisions` | 决策库 | 决策列表 + 语义搜索 + 分页 |
| `/decisions/:id` | 决策详情 | 候选方案 + 理由 + 反对意见 + 关联决策 + 原文片段 |
| `/chat` | AI 对话 | 双路 RAG 流式对话（虚拟滚动） |
| `/knowledge` | 知识库 | 文档上传 + 检索 |
| `/agent-runs` | Agent 监控 | 运行统计 + 列表 |
| `/agent-runs/:id` | 运行详情 | 步骤 / 预算 / Tool 调用 / 审批 |

---

## License

MIT
