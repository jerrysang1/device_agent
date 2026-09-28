# 设备售后协同智能体 · Vibe Coding 项目导师手册

> 面向零基础：每一轮只做一小步，改代码 → 跑起来 → 看现象 → 再进下一步。
> 配套：`设备售后协同智能体_架构与改造方案.md`、`atgui_agent/`、`device-service-backend/`、`shopkeeper_brain`（RAG）。
> **当前进度：只做到 state（领域模型层）**，见文末「进度打卡」。

---

## 0. 导师原则（三条铁律）

1. **一次只做一小步**：一轮对话只改 1 个功能点，做完就跑起来看效果。
2. **先能跑，再完美**：mock / 写死也能接受，链路通了再换真接口。
3. **每轮说清五句**再改代码：

```text
① 现状       中台 / 前端 / RAG / Agent 各自是否已启动
② 这轮目标   一句话说清本轮唯一目标
③ 入口在哪   例如 POST /api/chat
④ 期望行为   用户输入什么 → 系统应该做什么
⑤ 怎么验收   具体命令或界面现象；以及「这轮不做什么」
```

报错时贴**完整终端输出**，不要只说「跑不起来」。

---

## 1. 你现在的家底

| 资产 | 路径 | 作用 | 状态 |
|---|---|---|---|
| 改造方案 | `device_agent/设备售后协同智能体_架构与改造方案.md` | 蓝图 | 已有 |
| 业务中台 | `device_agent/device-service-backend`（:18082） | 设备/保修/工单/转人工 | 代码已有 |
| 工作台前端 | `atgui_agent/device-service-frontend`（:5173） | 对话 + 侧边栏 | 已有 |
| RAG | `E:\AAA message get\shopkeeper_brain`（:8001） | 手册问答 | 可选 |
| Agent 包 | `atgui_agent/agent_gateway`（:8100） | 意图→规划→工具→回复 | **领域层完成** |
| 统一环境 | `device_agent\.venv` | 唯一 Python 环境 | 已就绪 |
| 统一配置 | `atgui_agent/.env` | LLM / 中台 / DB / RAG | 已就绪 |

```text
用户说话
  → 前端 :5173
  → Agent 网关 :8100          ← 你在写这一层
      ├→ 中台 :18082          设备/保修/工单/转人工
      └→ RAG :8001            手册知识（可选，经中台）
```

---

## 2. 分层与编写顺序

```text
agent_gateway/
├── config/            统一配置（已完成）
├── infrastructure/    llm / http_client / database（已完成）
├── domain/            messages / contexts / state（已完成 ← 你在这里）
├── repository/        状态持久化（未学）
├── service/           load → process → save（未学）
├── engine/            调度与路由（未学）
├── plan/              LLM 规划 + 校验（未学）
├── task/              YAML 流程执行（未学）
├── knowledge/         手册问答（未学）
├── chitchat/          闲聊（未学）
├── prompts/           Prompt 模板（未学）
└── api/               FastAPI 路由（未学）
```

**建议编码顺序**：domain → repository/service → api → engine/task → plan。

**调用链（贴墙上）：**

```text
POST /api/chat
  → api（协议转换）
  → service（load → process → save）
  → engine（调度）
       ├→ plan（意图/计划，可先 stub）
       ├→ task（YAML 步骤推进）
       ├→ knowledge（RAG）
       └→ chitchat
  → 中台工具（http_client）
```

---

## 3. 每一轮工作循环

```text
① 说清五句 → ② 改代码 → ③ 按命令验收 → ④ 通过则打卡 / 失败贴完整报错 → ⑤ 下一轮
```

---

## 4. 分阶段路线图

### 阶段 0：地基跑通
中台 `/docs` + 前端侧边栏有设备/工单。

```powershell
cd F:\AAA求职相关\device_agent\atgui_agent
docker compose up --build
# 另开
cd F:\AAA求职相关\device_agent\atgui_agent\device-service-frontend
npm install
npm run dev
```

### 阶段 1：最小 Agent（建议下一轮）
用户发一句话 → 网关回一句话（关键词路由即可，**不上 LLM**）。

- 入口：`POST /api/chat`、`GET /api/chat/history`
- 行为：保修 → 调中台 warranty；人工 → transfers；其它 → 能力说明
- **禁止**：LLM、YAML 执行器、中断恢复

### 阶段 2：接 RAG 手册问答
问配置类问题 → 带引用答案；RAG 未启动时显式 `not_configured`，禁止假引用。

### 阶段 3：工单多轮 + confirmed
收集设备/故障 → **用户确认** → 写操作；`confirmed=true` 不可单独信任。

### 阶段 4：YAML 流程引擎
把 if-else 挪进 `flow_config/*.yml`（文件已备好）。

### 阶段 5：TurnPlan + Validator + LLM
LLM 只出 JSON，代码校验后执行。

### 阶段 6：中断恢复 + 评测
`paused_tasks` 压栈/恢复；20 条场景评测。

---

## 5. 中台 API 速查

Base：`http://127.0.0.1:18082`（详见 `API.md` / `/docs`）

| 工具 | 权限 | 接口 |
|---|---|---|
| check_warranty | read | `GET /devices/{id}/warranty` |
| get_device_profile | read | `GET /devices/{id}` |
| create_service_ticket | write_confirm | `POST /devices/{id}/tickets` |
| get_repair_progress | read | `GET /tickets/{id}/repair` |
| transfer_to_human | write_confirm | `POST /transfers` |
| search_manual | read | `POST /manual/search` |

写操作必须 `confirmed=true`；HTTP 走 `infrastructure/http_client.py`。

---

## 6. 常见坑

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 跨盘 cd 无效 | cmd 默认不切盘 | `cd /d` |
| `import agent_gateway` 失败 | 解释器不对 | 选 `device_agent\.venv` |
| 建表找不到 | 表在远程 `device_service` | Navicat 连对应主机 |
| 前端报 Agent 未启动 | :8100 未起 | 阶段 1 之后再起 |
| 手册答案像模板 | RAG 未起 | 保持 not_configured，勿伪装 |

---

## 7. 你现在立刻做的 3 件事

1. **确认进度**：领域层 messages / contexts / state 是否都跑过自测。
2. **锁定下一轮**：只做「阶段 1：最小 Agent 保修 + 转人工」。
3. **开场白模板**：

```text
现状：中台（已/未）跑起来，前端（已/未）跑起来
这轮目标：阶段1 最小 Agent
入口：POST /api/chat
期望：识别保修意图 → 调中台 warranty → 中文回复
验收：curl 查 DEV-2026-0001 保修能返回真实天数
不做：LLM、工单多轮、中断恢复
```

---

## 8. 进度打卡

> **当前进度：只做到 state（领域模型层）。**
> 已完成：`config`、`infrastructure`（llm/http/database）、`domain/messages.py`、`domain/contexts.py`、`domain/state.py`。
> **api / service / engine / task / plan / RAG 接入都还没学完，不算完成。**
> 仓库中可能存在其他脚手架代码，不代表你已掌握——以本表为准继续 vibe。

| 阶段 | 内容 | 状态 | 备注 |
|---|---|---|---|
| 基建 | config / infrastructure / database | ✅ 已完成 | |
| 领域 | messages + contexts + **state** | ✅ 已完成 | **你目前停在这里** |
| 0 | 中台 + 前端跑通 | ⬜ 未开始 | |
| 1 | 最小 Agent（保修/转人工） | ⬜ 未开始 | 下一轮 |
| 2 | 接 RAG 手册问答 | ⬜ 未开始 | |
| 3 | 工单多轮 + confirmed | ⬜ 未开始 | |
| 4 | YAML 流程引擎 | ⬜ 未开始 | yml 已备好 |
| 5 | TurnPlan + Validator + LLM | ⬜ 未开始 | |
| 6 | 中断恢复 + 20 场景评测 | ⬜ 未开始 | |

---

## 9. 相关文件

- `README.md` — 项目总览与启动
- `启动说明.txt`（仓库根）— 唯一权威启动入口
- `API.md` — 中台 REST
- `docs/agent-integration.md` — Agent / RAG 对接
- `docs/01-设备售后协同智能体-项目概述与整体架构.md` §4.6 — 多智能体进阶
- `设备售后协同智能体_架构与改造方案.md`
