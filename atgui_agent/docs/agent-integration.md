# Agent 对接说明

本文说明 **设备售后协同智能体（DeviceCare Agent）** 如何调用本设备维修中台，以及与 RAG 项目的边界。

## 1. 职责边界

```text
device-rag / shopkeeper_brain
    如何解析、索引、召回和引用知识？

device-service（本中台）
    设备、保修、工单、转人工等确定性业务读写

device-service-agent（Agent 编排）
    什么时候查知识、什么时候查保修、什么时候创建工单
    DialogueState / TurnPlan / FlowExecutor / ToolRegistry
```

Agent **不复制** BGE-M3、Milvus、RRF、Rerank 等 RAG 内部实现；只通过 `POST /manual/search` 调用。

## 2. 工具映射

| Agent 工具 | 权限 | 中台接口 |
|---|---|---|
| `search_manual` | read | `POST /manual/search` |
| `get_device_profile` | read | `GET /devices/{device_id}` |
| `check_warranty` | read | `GET /devices/{device_id}/warranty` |
| `get_device_history` | read | `GET /devices/{device_id}/history` |
| `get_ticket_status` | read | `GET /tickets/{ticket_id}/status` |
| `get_repair_progress` | read | `GET /tickets/{ticket_id}/repair` |
| `create_service_ticket` | write_confirm | `POST /devices/{device_id}/tickets` |
| `update_service_ticket` | write_confirm | `PATCH /tickets/{ticket_id}` |
| `cancel_service_ticket` | write_confirm | `POST /tickets/{ticket_id}/cancel` |
| `transfer_to_human` | write_confirm | `POST /transfers` |

运行时可从 `GET /tools` 动态拉取，避免硬编码。

## 3. LLM 安全边界

LLM 只输出结构化计划，例如：

```json
{
  "route": "service",
  "task_type": "create_service_ticket",
  "slots": {
    "device_model": "H3C LA2608",
    "device_id": "DEV-2026-0001",
    "problem_type": "controller_connection"
  },
  "next_action": "ask_confirmation"
}
```

代码负责校验与执行：

1. `TurnPlanValidator` 校验 route 白名单、slot 完整、设备编号格式。
2. `write_confirm` 工具必须先向用户确认，再带 `confirmed=true` 调用。
3. 连续两次工具失败或用户主动要求时，调用 `transfer_to_human`。

## 4. 建议调用序列

### 保修查询

```text
extract device_id
  → GET /devices/{device_id}/warranty
  → NL 回复
```

### 工单创建（多轮）

```text
collect device_id / problem / tried_steps
  → GET /devices/{device_id}          # 校验设备存在
  → GET /devices/{device_id}/warranty # 可选，判断是否过保
  → ask_confirmation
  → POST /devices/{device_id}/tickets { confirmed: true, ... }
  → 返回 ticket_id
```

### 知识问答 + 排查

```text
identify model
  → POST /manual/search
  → 返回 answer + citations
  → 追问执行结果
  → 必要时 create_service_ticket
```

### 中断恢复

```text
当前任务：create_service_ticket（COLLECTING_SLOTS）
用户插问：这台设备还在保修期吗？
  → 原任务 → paused_tasks
  → 执行 check_warranty
  → 完成后恢复 paused_tasks
```

`DialogueState` 可持久化到 `customer_service.dialogue_states`（见 `mysql/initdb/002_init_customer_service.sql`）。

## 5. 手册 RAG 对接契约（shopkeeper_brain）

真实 RAG 项目路径：`E:\AAA message get\shopkeeper_brain`  
默认地址：`http://127.0.0.1:8001`（`python main.py` / uvicorn 8001）

中台 `POST /manual/search` 会调用：

```http
POST {RAG_BASE_URL}/query
Content-Type: application/json

{
  "query": "H3C LA2608 怎么配置业务 VLAN？",
  "is_stream": false,
  "session_id": "可选"
}
```

要点：
- 中台把 `device_model` 拼进 `query`，配合 RAG 内部商品名消歧。
- `is_stream=false` 走同步 `QueryResponse`（`answer` + `sources`）。
- `sources[].{file_title,title,parent_title,snippet,score,item_name}` 映射为 `citations`。

期望 RAG 返回（`QueryResponse`）：

```json
{
  "message": "查询请求已经处理完了",
  "session_id": "…",
  "answer": "……",
  "sources": [
    {
      "index": 1,
      "title": "业务 VLAN 配置",
      "parent_title": "配置指南",
      "file_title": "H3C LA2608室内无线网关 用户手册",
      "item_name": "H3C LA2608",
      "source": "local",
      "snippet": "……",
      "score": 0.92
    }
  ]
}
```

也兼容嵌套在 `data` 下的同名字段。失败时中台回退 stub，保证 Agent 链路可演示。

本地启动 RAG：

```powershell
cd "E:\AAA message get\shopkeeper_brain"
knowledge\.venv\Scripts\python.exe -m uvicorn knowledge.api.query_router:create_app --factory --port 8001
# 或：knowledge\.venv\Scripts\python.exe main.py --port 8001
```

## 6. 转人工返回约定

```json
{
  "request_type": "transfer_to_human",
  "request_id": "HUM-...",
  "ticket_id": "TKT-2026-000001",
  "status": "transferred",
  "status_desc": "已转接人工客服，请稍候。"
}
```

Agent 可将 `status=transferred` 与 `reason` 一并写回对话，并结束当前任务为 `TRANSFERRED`。

## 7. 前端 Chat 网关（预留）

前端 `/api/chat` 与 `/api/chat/history` 由 Agent 网关实现（默认 `127.0.0.1:8100`），与本中台分离：

```text
Vue 工作台
  ├─ /api/*     → Agent Chat API（SSE/JSON）
  └─ /device/*  → 设备维修中台 18082
```

中台侧边栏不依赖 Agent 即可独立查询设备与工单。

## 8. 评测建议（Agent 场景集）

评测 Agent 行为而非仅最终话术：

- 路由准确率（knowledge / service / chitchat）
- 工具选择准确率（是否调用正确工具、是否多余调用）
- 参数槽位准确率（device_id / model / problem）
- 流程完成率
- 安全拦截率（confirmed 是否被强制）
- 状态恢复成功率
- 成本与延迟

场景样例见架构方案 §10–§12。
