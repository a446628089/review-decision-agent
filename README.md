# Review Decision Agent｜研发评审智能决策平台

面向研发团队的会议决策提取与检索平台。将评审录音转为文字，通过 Agent 提取纪要、行动项、风险和决策，再将决策与文档知识纳入 RAG 问答，帮助团队追溯“做了什么决定、有哪些备选方案、为什么这样选”。

前端使用 **React 19 + TypeScript** 构建会议管理、决策库、知识库和流式对话界面；后端通过 **FastAPI + LangGraph + PostgreSQL / pgvector** 完成会议处理与检索。

## 核心亮点

### 两阶段决策抽取

基于 **LangGraph** 编排决策抽取流程，先定位决策片段，再逐段提取候选方案、选择理由与反对意见。通过节点容错与自研三级 JSON 降级解析，将结构化输出失败率控制在 **1% 以下**。

### 混合检索与多轮问答

基于 **PostgreSQL + pgvector** 构建混合检索 RAG，采用向量与全文双路召回、**RRF（k=60）** 融合、关键词重排与内容去重。通过查询改写处理多轮对话中的指代，将问题与相关评审内容对应起来。

对话侧同时检索会议纪要、知识文档与结构化决策，融合后生成回答，并展示引用来源。

### Agent Harness 稳定性治理

自研 **Agent Harness 约束层**，通过装饰器包裹业务节点、**ContextVar** 传递运行上下文，提供预算控制、熔断、指数退避重试工具及 **Pydantic** 校验，覆盖**成本、熔断、重试、输出校验 4 类稳定性治理**。运行监控界面展示步骤、耗时、Token 消耗与估算成本，便于定位执行问题。

### 历史决策预关联

决策写入时预计算并关联 **Top-3 相似历史决策**，将相似度计算前移至写入阶段。查询时直接读取已存储的关联关系，减少重复计算，支持跨会议追溯与方案比较；相似度低于阈值的结果不建立关联。

### React 流式交互与性能优化

- **流式对话**：使用原生 `fetch + ReadableStream` 消费 SSE，增量显示回答，支持 Markdown、代码高亮与来源展示。
- **长列表渲染**：使用 **@tanstack/react-virtual** 支持千级消息虚拟化渲染，动态测量消息高度，降低长会话列表的渲染开销；转写列表复用虚拟列表能力。
- **加载优化**：通过 **Vite 分包、路由懒加载及 gzip 预压缩**优化首屏资源加载。部署时需由静态资源服务配置压缩文件响应。
- **状态管理**：使用 TanStack Query 管理服务端数据，Zustand 管理界面状态。

## 技术栈与架构

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite 8、React Router 7、Tailwind CSS 4 |
| 状态与交互 | TanStack Query 5、Zustand 5、TanStack Virtual、SSE、react-markdown |
| 后端 | FastAPI、SQLAlchemy 2 Async、Alembic、Pydantic |
| Agent | LangGraph、通义千问、Agent Harness |
| 检索与存储 | PostgreSQL 16、pgvector、text-embedding-v3（1024 维） |
| 录音与文档 | DashScope Paraformer-v2、阿里云 OSS、pypdf、python-docx |
| 本地基础设施 | Docker Compose；Redis 容器预留，尚未接入业务 |

```mermaid
flowchart TD
    UI[React 前端] --> API[FastAPI]
    API --> Audio[录音上传与转写]
    Audio --> Text[会议文本]
    Text --> Graph[LangGraph 工作流]
    Graph --> Planner[Planner 动态调度]
    Planner --> Agents[纪要 / 行动项 / 风险 / 决策抽取]
    Agents --> Store[PostgreSQL + pgvector]
    Docs[知识文档] --> Store
    API --> Chat[AI 对话]
    Chat --> Retrieval[文档与决策双路 RAG]
    Store --> Retrieval
    Retrieval --> LLM[上下文融合与模型生成]
    LLM --> SSE[SSE 流式响应]
    SSE --> UI
```

**使用流程**：创建会议并上传录音 → 自动转写 → 在纪要页触发生成 → 查看纪要与结构化决策 → 在决策库追溯关联，在 AI 对话中检索问答。

Planner 按会议内容选择需要执行的业务 Agent，并行生成相应结果；生成后的纪要和决策由业务服务写入数据库并建立索引。

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

## 项目结构

```text
.
├── frontend/
│   ├── src/features/       # 会议、纪要、决策、对话、知识库与运行监控
│   ├── src/components/     # 布局与通用组件
│   ├── src/hooks/          # 虚拟列表与语音交互
│   ├── src/api/            # HTTP 请求与 SSE 消费
│   └── vite.config.ts     # 构建、分包与 gzip 预压缩
├── backend/
│   ├── app/agents/         # LangGraph 节点、Harness 与工具注册
│   ├── app/services/       # 转写、决策、知识索引与 RAG
│   ├── app/api/            # FastAPI 路由
│   ├── app/models/         # 数据模型
│   ├── alembic/            # 数据库迁移
│   ├── scripts/            # 冒烟与流程验证脚本
│   └── .env.example        # 环境变量模板
├── sfu/                   # 保留的实时会议实验服务
├── docker-compose.yml     # 本地数据库与 Redis
├── dev.cmd / dev.ps1       # Windows 启动入口
└── stop.cmd / stop.ps1     # Windows 停止入口
```

完整接口与参数可在启动后查看 [API 文档](http://localhost:8787/docs)。

## 当前边界

- 当前主流程处理上传的录音；实时会议服务未接入默认启动链路。
- 人工审批已有界面与状态接口，尚未实现工作流暂停与审批后恢复。
- 决策检测阶段读取输入前 8,000 个字符，长文本压缩后仍可能遗漏细节。
- Harness 中的指数退避工具已实现；主工作流目前使用有限次数重试，尚未接入该工具。
- Mock 转写用于体验流程，不识别上传录音的实际内容；模型生成与向量检索仍需配置可用的 API。

## License

MIT
