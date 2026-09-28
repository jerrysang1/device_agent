# 设备售后协同智能体（DeviceCare Agent）

面向设备售后场景的对话工作台：用户用自然语言查保修、问手册、报修建单；Agent 负责理解与规划，中台负责确定性业务。

> 演示数据为脱敏设备样例与合成工单，不包含真实用户数据。  
> **权威启动说明**见仓库根：`F:\AAA求职相关\device_agent\启动说明.txt`。

## 真实目录结构

```text
device_agent\                            仓库根（.venv 统一环境）
├── device-service-backend\              业务中台 :18082（不在 atgui_agent 下）
├── mysql\initdb\                        MySQL 初始化 SQL
├── pyproject.toml                       唯一依赖清单
└── atgui_agent\
    ├── agent_gateway\                   Agent 网关 :8100
    ├── device-service-frontend\         Vue 工作台 :5173
    ├── flow_config\                     YAML 流程
    ├── .env / .env.example              统一配置
    ├── docker-compose.yml               仅 MySQL + 中台（不含 Agent）
    ├── API.md                           中台 REST 说明
    └── docs\agent-integration.md        Agent / RAG 对接
```

## 功能矩阵（以运行验证为准）

| 能力 | 状态 | 说明 |
|---|---|---|
| 中台设备/保修/工单/转人工 API | 代码已有，待运行验证 | `device-service-backend` |
| Agent `/health` | **已实现，测试通过** | 未起进程时端口无监听 |
| 聊天 `/api/chat`、`/api/chat/history` | **已实现，测试通过** | 出参字段对齐前端 |
| 保修查询闭环（Agent→中台） | **已实现，测试通过** | stub_brain 关键词路由 |
| 知识问答 | 明确 `not_configured` | 不伪造手册 |
| AGENT_API_KEY 服务间认证 | **已实现** | 配置后强制请求头 |
| 工单号生成 | **已修** | max+1，唯一约束兜底 |
| 手册问答（RAG） | 计划中 | 不可用时必须 `source=stub`/`not_configured` |
| YAML 流程执行器 | 计划中 | YAML 已备好 |
| LLM 结构化规划 | 计划中 | `infrastructure/llm.py` 已备好 |
| 用户级授权/确认令牌 | **未完成（残留风险）** | 仅有 `confirmed=true`，无会话绑定令牌 |

**模拟/降级约定**：RAG 未启动时，任何手册类回答必须显式标记模拟或不可用，禁止伪造 PDF 引用。

## 快速启动

请按仓库根 `启动说明.txt`；摘要：

```powershell
# MySQL + 中台
cd F:\AAA求职相关\device_agent\atgui_agent
docker compose up --build

# 前端
cd F:\AAA求职相关\device_agent\atgui_agent\device-service-frontend
npm install
npm run dev
```

## 服务地址

| 服务 | 地址 | 状态 |
|---|---|---|
| 中台 API | http://127.0.0.1:18082/docs | 以实际启动为准 |
| 前端工作台 | http://127.0.0.1:5173 | 以实际启动为准 |
| Agent 网关 | http://127.0.0.1:8100 | 见功能矩阵 |

前端代理：`/device/*` → 中台，`/api/*` → Agent；默认 `127.0.0.1`，可用 `VITE_DEVICE_API_BASE` / `VITE_AGENT_API_BASE` 覆盖。

## 演示账号（合成数据）

| sender_id | 设备 | 工单 |
|---|---|---|
| `u1001` | DEV-2026-0001 / DEV-2026-0004 | TKT-2026-000001 |
| `u1002` | DEV-2026-0002 | TKT-2026-000003 |
| `u1003` | DEV-2026-0003 | TKT-2026-000002 |

## 架构边界

```text
Vue 工作台（5173）
  ├── /api/*    → Agent Gateway（8100）：会话、意图、任务状态、工具调用
  └── /device/* → Device Service（18082）：设备/保修/工单等确定性 API
                     └── /manual/search → shopkeeper_brain RAG（8001，可选）
```

- 模型输出必须经白名单与参数校验；禁止直接访问数据库或任意 SQL。
- 写操作在服务端校验授权与确认；客户端 `confirmed=true` 不可单独信任。

## 安全说明

- 本项目为**本地演示**：未实现完整用户登录；请勿公网暴露。
- `.env` 中含密钥，已由 `.gitignore` 忽略；发现泄露请自行轮换。
- 详见任务单阶段 3 的授权边界说明。

## 文档

- [API.md](API.md) — 中台 REST
- [docs/agent-integration.md](docs/agent-integration.md) — Agent / RAG 对接
- [VIBE_CODING_GUIDE.md](VIBE_CODING_GUIDE.md) — 开发路线
- [docs/01-设备售后协同智能体-项目概述与整体架构.md](docs/01-设备售后协同智能体-项目概述与整体架构.md)
