# 研发评审智能决策平台

> 面向研发评审场景的 **离线会议决策提取与检索平台**。上传评审录音 → 转写 → Multi-Agent 并行提取纪要/行动项/风险/决策 → 决策入库向量化 → AI 对话双路 RAG 召回。

---

## 核心能力

### 离线会议处理链路

```text
创建会议并上传录音
  → 后台转写（DashScope ASR / Mock）
  → 保存转写文本、说话人和时间戳
  → 用户在纪要页触发生成
  → Planner 选择本次需要执行的 Agent
      ├─ 摘要 Agent        → 纪要与要点
      ├─ 行动项 Agent      → 待办、负责人、截止日期
      ├─ 风险 Agent        → 风险与缓解建议
      └─ 决策抽取 Agent    → 决策与候选方案
  → SummaryService 落库、索引纪要并保存决策
  → 决策向量化，关联最多 3 个相似决策
```

上传后自动执行转写，纪要生成需要另行触发。四类业务 Agent 按 Planner 的计划动态并行执行，并非每次都会全部运行。

### 决策抽取两步流水线

| 步骤 | 节点 | 职责 |
|------|------|------|
| Step 1 | `DecisionDetector` | 读取输入文本前 8,000 个字符，定位决策段；仅保留 `type=decision` 且 `confidence ≥ 0.7` 的结果 |
| Step 2 | `OptionExtractor` | 结合决策片段前后各 500 个字符的上下文，抽取标题、背景、候选方案、已选方案、理由、反对意见与决策人 |

### Harness 约束框架

四类业务 Agent 通过 `harness_wrap` 接入超时、熔断和执行记录；Planner、文本压缩、输出校验和审批预留节点没有套用这一装饰器。

- **预算**：`BudgetGuard` 累计 Token 与估算成本，超限抛出 `BudgetExceededError`；`run_id` 和预算对象通过 ContextVar 传递。
- **超时与熔断**：摘要、行动项、风险节点超时为 60 秒，决策抽取为 120 秒；连续失败由共享熔断器控制。
- **结构化校验**：摘要、行动项与风险输出校验失败后，每个节点最多回灌重试 2 次；决策抽取使用内部 Pydantic 模型校验。
- **运行记录**：`AgentRun` 保存步骤、耗时、Token 和成本等信息，前端提供运行列表、详情与工具注册表展示。

主流程的基础 LLM 调用使用 `_invoke_with_retry` 做有限次数重试；`retry.py` 中的 `with_smart_retry` 提供指数退避工具，目前未接入主工作流。

### 双路 RAG 召回

AI 对话结合最近 10 条消息，在需要时改写查询，再依次检索文档路和决策路（串行调用），用 RRF 融合后送入 LLM：

```
用户提问
  → 文档路：knowledge_service.search(top_k=3)（纪要 + 知识文档）
  → 决策路：decision_graph_service.search(top_k=3)（决策语义检索）
  → RRF 融合（k=60）→ 最多 5 条上下文
  → LLM 流式输出（SSE）
```

文档路内部使用向量检索与 PostgreSQL 全文检索，经过 RRF 融合、关键词重排和相似内容去重。查询向量不可用时降级为全文检索，全文检索异常时尝试 `ILIKE`。

---

## 技术栈

### 后端

| 领域 | 技术 |
|---|---|
| Web 框架 | FastAPI 0.115 + Uvicorn |
| 数据库 | PostgreSQL 16 + pgvector（cosine, ivfflat, 1024 维） |
| ORM | SQLAlchemy 2.0（async）+ Alembic |
| 预留缓存服务 | Redis 7（已配置容器与 URL，业务代码尚未接入） |
| Agent 编排 | LangGraph 0.2.70（StateGraph + 条件路由 + 动态 fan-out） |
| LLM | 默认 qwen-plus；含图片的对话使用 qwen-vl-plus（均可配置） |
| Embedding | text-embedding-v3（1024 维） |
| ASR | DashScope Paraformer-v2（录音文件识别，OSS 中转） |
| 文档解析 | pypdf / python-docx / UTF-8 文本读取（PDF、DOCX、TXT、Markdown） |

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
| 向量存储 | pgvector（PostgreSQL 扩展，决策与知识文档均使用 1024 维向量） |

---

## 系统架构

```text
React 前端（会议 / 纪要 / 决策 / 对话 / 知识库 / Agent 监控）
  │ HTTP / SSE；开发时 Vite 将 /api 代理到 localhost:8787
  ▼
FastAPI 路由 → 业务服务 → PostgreSQL + pgvector
                 │
                 ├─ 转写：OSS 中转 → DashScope ASR → 轮询结果
                 ├─ 纪要：LangGraph 工作流 → 纪要与决策落库
                 └─ 对话：文档检索 + 决策检索 → RRF → LLM 流式回答
```

默认使用项目内的 v2 工作流，`v2` 指 `meeting_graph_v2.py`，不是 LangGraph 依赖的主版本号：

```text
planner → budget_check → 按计划并行执行业务 Agent
  → output_validator ──校验失败且未达重试上限──→ 对应 Agent
  → human_review → persist → END
```

`budget_check` 根据计划对超长文本尝试 LLM 压缩；实际 Token/成本上限由 `BudgetGuard` 在调用过程中控制。`human_review` 当前直接放行，`persist` 仅标记图完成；数据库写入与知识索引由 `SummaryService` 处理。

---

## 项目结构

以下以仓库根目录 `./` 为起点，列出主要源码与配置，省略包初始化文件、依赖目录和运行产物。

```text
./
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── harness/                 # 预算、熔断、重试工具、校验与装饰器
│   │   │   ├── nodes/                   # Planner、压缩、决策抽取、输出校验、审批预留
│   │   │   ├── tools/                   # 工具注册表与会议操作封装
│   │   │   ├── meeting_graph.py         # 基础图与通用 LLM 调用
│   │   │   └── meeting_graph_v2.py      # 默认工作流：动态调度 + Harness
│   │   ├── api/
│   │   │   ├── health.py                # 数据库健康检查
│   │   │   ├── deps.py                  # Session 与会议查询依赖
│   │   │   ├── meetings.py              # 会议 CRUD、音频与转写
│   │   │   ├── summaries.py             # 纪要、行动项与风险
│   │   │   ├── decisions.py             # 决策列表、详情与搜索
│   │   │   ├── chat.py                  # 会话管理与 SSE
│   │   │   ├── knowledge.py             # 文档上传、索引与检索
│   │   │   ├── agent_runs.py            # 运行记录、统计、工具列表与审批状态
│   │   │   └── rooms.py                 # 已注册的房间 API，依赖单独启动的 SFU
│   │   ├── services/
│   │   │   ├── meeting_service.py       # 会议管理与录音存储
│   │   │   ├── transcription_service.py # 转写 Provider 选择与落库
│   │   │   ├── dashscope_asr_service.py # ASR 任务提交、轮询与解析
│   │   │   ├── oss_service.py           # 录音中转与临时对象清理
│   │   │   ├── summary_service.py       # 工作流调用、落库与纪要索引
│   │   │   ├── decision_graph_service.py # 决策入库、向量关联与检索
│   │   │   ├── chat_service.py          # 双路 RAG 与流式回答
│   │   │   ├── knowledge_service.py     # 知识索引、混合检索与管理
│   │   │   ├── embedding_service.py     # 文本向量化
│   │   │   ├── agent_run_service.py     # AgentRun 生命周期与记录
│   │   │   ├── document_parser.py       # 文档解析
│   │   │   ├── document_chunker.py      # 文本分块
│   │   │   └── sfu_bridge.py            # SFU HTTP 客户端
│   │   ├── models/                      # ORM：会议、纪要、决策、知识、对话、运行等
│   │   ├── schemas/                     # Pydantic 请求与响应模型
│   │   ├── db/                          # ORM Base 与异步数据库连接
│   │   ├── config.py                    # 环境变量配置
│   │   └── main.py                      # FastAPI 入口、CORS 与路由注册
│   ├── alembic/
│   │   ├── versions/                    # 数据库迁移链
│   │   └── env.py                       # Alembic 异步迁移环境
│   ├── scripts/                         # 冒烟测试、转写与端到端验证脚本
│   ├── alembic.ini
│   ├── seed_data.py                     # 清除相关旧数据后灌入演示数据
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── public/                          # 静态资源与音频处理脚本
│   ├── src/
│   │   ├── features/
│   │   │   ├── meetings/                # 会议列表、创建、上传与详情
│   │   │   ├── summaries/               # 纪要列表、生成、行动项与风险
│   │   │   ├── decisions/               # 决策列表、搜索与详情
│   │   │   ├── chat/                    # 流式对话与消息虚拟列表
│   │   │   ├── knowledge/               # 文档上传、检索与管理
│   │   │   └── agent-runs/              # 运行监控与审批界面
│   │   ├── components/
│   │   │   ├── layout/                  # 页面布局、侧栏与页头
│   │   │   └── ui/                      # 通用组件与 Markdown 渲染
│   │   ├── api/                         # ky 请求封装与 fetch SSE 解析
│   │   ├── assets/                      # 图片与 SVG 资源
│   │   ├── hooks/                       # 虚拟列表、语音输入与朗读
│   │   ├── lib/                         # 常量、工具与 QueryClient
│   │   ├── router/                      # 懒加载路由
│   │   ├── stores/                      # Zustand UI 状态
│   │   ├── types/                       # TypeScript 类型
│   │   ├── App.tsx                      # 应用 Provider 与路由容器
│   │   ├── main.tsx                     # React 入口
│   │   └── index.css                    # 全局样式
│   ├── index.html
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── tsconfig.node.json
│   └── vite.config.ts                   # 构建、分包与开发代理
├── sfu/                                 # 保留的 mediasoup 服务，未接入默认启动链路
├── docker-compose.yml                   # PostgreSQL + pgvector、Redis
├── dev.ps1                              # Windows 启动脚本
├── dev.cmd                              # 启动脚本入口
├── stop.ps1                             # 停止双端与容器
├── stop.cmd                             # 停止脚本入口
├── .gitignore
├── AGENTS.md                            # 项目工作约定
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
├─ id (UUID, PK)
├─ source_decision_id (FK → decisions)
├─ target_decision_id (FK → decisions)
├─ relation_type (default 'relates')
├─ context (text) / similarity_score (float)
├─ created_at
└─ UNIQUE(source_decision_id, target_decision_id)
```

关联写入时排除当前决策，从最多 3 个近邻中保留相似度不低于 0.7 的结果，写入双向 `relates` 关系；查询未限定为其他会议。

### 其他核心表

`meetings` / `transcripts` / `summaries` / `action_items` / `risks` / `knowledge_documents` / `agent_runs` / `chat_sessions` / `chat_messages`

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 22.12+（Vite 8 要求 Node.js 20.19+ 或 22.12+）
- pnpm 10.20.0（与 `frontend/package.json` 一致）
- Docker（用于 PostgreSQL + Redis）

### 获取项目与安装依赖（Windows PowerShell）

```powershell
git clone https://github.com/a446628089/DdddkVerdict.git
cd DdddkVerdict

python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
# 编辑 backend/.env，填入自己的 OPENAI_API_KEY

Push-Location frontend
pnpm install --frozen-lockfile
Pop-Location
```

已有 `backend/.env` 时跳过复制步骤，保留自己的配置。

### 方式一：Windows 一键启动

在仓库根目录执行：

```powershell
.\dev.cmd -NoSeed
```

脚本会启动 Docker 容器、等待 PostgreSQL、启用 `vector` 扩展、执行迁移，并在后台启动后端 8787 与前端 5173，将日志汇总到当前终端。运行前需完成依赖安装和 `.env` 配置。

**默认执行 `.\dev.cmd` 会运行 `seed_data.py`，清除旧会议、转写、纪要、行动项、风险及相关知识文档后灌入演示数据。** 日常开发使用 `-NoSeed`；仅在可重置的演示数据库上使用默认命令。

按 `Ctrl+C` 会停止本次启动的前后端进程，保留 Docker 容器。执行 `.\stop.cmd` 会停止占用 5173、8787 端口的进程以及本项目容器，保留数据库卷。

### 方式二：手动启动

先在仓库根目录启动基础设施并启用扩展，扩展必须在首次迁移前创建：

```powershell
docker compose up -d --wait
docker compose exec -T postgres psql -U postgres -d yuan_meet -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

终端一，从仓库根目录启动后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8787
```

终端二，从仓库根目录启动前端：

```powershell
cd frontend
pnpm run dev
```

Linux/macOS 可在 `backend/` 中通过 `python -m venv .venv`、`source .venv/bin/activate` 创建并激活环境，使用 `python -m pip`、`python -m alembic` 和 `python -m uvicorn` 执行对应步骤；复制配置使用 `cp .env.example .env`。根目录启停脚本用于 Windows。

### 访问地址

- 前端：[http://localhost:5173](http://localhost:5173)
- API 文档：[http://localhost:8787/docs](http://localhost:8787/docs)
- 数据库健康检查：[http://localhost:8787/api/health](http://localhost:8787/api/health)
- PostgreSQL：`127.0.0.1:15432`（容器内 5432）；Redis：`127.0.0.1:6379`。

Vite 将 `/api` 代理到 `http://localhost:8787`。前端端口 5173 被占用时可能自动递增，以终端输出为准，并相应调整后端 `CORS_ORIGINS`。

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
VISION_MODEL=qwen-vl-plus
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIMENSIONS=1024

# 音频转写
# auto: 优先真实转写，未配置 OSS 时自动降级 Mock（默认）
# mock: 仅模拟转写（不会识别上传录音的实际内容）
# dashscope: 仅真实转写
TRANSCRIPTION_PROVIDER=auto

# DashScope ASR：不填独立 Key 时复用 OPENAI_API_KEY
# DASHSCOPE_API_KEY=
DASHSCOPE_ASR_MODEL=paraformer-v2

# 阿里云 OSS（真实转写需要；auto 模式下不可用时降级 Mock）
# OSS_ACCESS_KEY_ID=
# OSS_ACCESS_KEY_SECRET=
# OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
# OSS_BUCKET_NAME=

UPLOAD_DIR=./uploads
CORS_ORIGINS=["http://localhost:5173"]
```

**Mock 转写体验**：完成依赖安装、数据库迁移并填入 `OPENAI_API_KEY` 后，可使用 Mock 转写体验主流程。Mock 使用内置示例语料，不代表上传录音的真实内容；纪要、决策抽取和 RAG 仍需可用的模型与向量服务。

**真实音频转写**：额外配置 4 个 OSS 环境变量，音频上传 OSS → 提交 DashScope ASR 任务 → 轮询解析（含说话人 + 时间戳）→ 清理 OSS。

---

## API 概览

| 模块 | 方法与路径 | 说明 |
|---|---|---|
| 健康检查 | `GET /api/health` | 应用与数据库状态 |
| 会议 | `GET /api/meetings`、`POST /api/meetings` | 分页列表、创建会议 |
| 会议 | `GET /api/meetings/{meeting_id}` | 会议详情 |
| 会议 | `POST /api/meetings/{meeting_id}/upload` | multipart 上传录音，后台转写 |
| 会议 | `GET /api/meetings/{meeting_id}/transcripts` | 转写片段 |
| 会议 | `GET /api/meetings/{meeting_id}/transcription-status` | 转写状态与片段数量 |
| 纪要 | `GET /api/summaries` | 纪要列表 |
| 纪要 | `POST /api/meetings/{meeting_id}/summarize` | 执行 Agent 工作流，等待生成结果 |
| 纪要 | `GET /api/meetings/{meeting_id}/summary` | 纪要、行动项与风险 |
| 决策 | `GET /api/decisions` | 分页列表，可按会议筛选 |
| 决策 | `GET /api/decisions/search` | 使用查询参数 `q` 语义搜索 |
| 决策 | `GET /api/decisions/{decision_id}` | 候选方案与关联决策等详情 |
| 对话 | `POST /api/chat/sessions` | 创建对话会话 |
| 对话 | `POST /api/chat/sessions/{session_id}/stream` | SSE 流式回答，事件类型为 `token`、`done`、`error` |
| Agent | `GET /api/agent-runs` | 运行列表 |
| Agent | `GET /api/agent-runs/stats/overview` | 运行统计 |
| Agent | `GET /api/agent-runs/tools/list` | 工具注册表 |
| Agent | `GET /api/agent-runs/{run_id}` | 运行详情 |
| Agent | `POST /api/agent-runs/{run_id}/review` | 更新审批状态，尚未接通图恢复 |
| 知识 | `POST /api/knowledge/search` | JSON 请求体：`{"query":"检索内容","top_k":5}` |
| 知识 | `POST /api/knowledge/upload` | multipart 上传文档并索引 |
| 知识 | `POST /api/knowledge/index` | 直接索引文本 |
| 知识 | `GET /api/knowledge/documents` | 文档块列表 |
| 知识 | `DELETE /api/knowledge/documents/{doc_id}` | 按所选文档块的标题删除相关块 |

完整接口与参数以运行后的 [OpenAPI 文档](http://localhost:8787/docs) 为准。

---

## 前端页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 会议列表 | 创建会议、选择录音并上传 |
| `/meetings/:id` | 会议详情 | 录音播放、转写、关联决策与纪要入口 |
| `/summaries` | 纪要列表 | 所有会议纪要 |
| `/summaries/:id` | 纪要详情 | `id` 为会议 ID；生成/查看纪要、行动项与风险 |
| `/decisions` | 决策库 | 决策列表 + 语义搜索 + 分页 |
| `/decisions/:id` | 决策详情 | 候选方案 + 理由 + 反对意见 + 关联决策 + 原文片段 |
| `/chat` | AI 对话 | 双路 RAG 流式对话（虚拟滚动） |
| `/knowledge` | 知识库 | 文档上传 + 检索 |
| `/agent-runs` | Agent 监控 | 运行统计 + 列表 |
| `/agent-runs/:id` | 运行详情 | 步骤、预算、工具调用记录与审批状态 |

---

## 当前边界

- **人工审批**：界面与审批状态接口已存在，工作流的审批节点目前直接放行；尚无完整的暂停、审批、恢复执行流程。
- **实时会议**：保留 `sfu/`、房间 API 和实时会话模型；房间 API 已注册，但前端没有启用房间页面，默认 Compose 与启动脚本也不启动 SFU。
- **Redis**：已声明依赖、连接地址与容器，当前业务代码尚未实际使用缓存或任务队列。
- **长文本决策抽取**：检测阶段截取输入前 8,000 个字符；即使使用压缩文本，也不保证覆盖长录音中的全部决策。

---

## License

MIT
