# 设备维修中台 API 文档

> Base URL：`http://127.0.0.1:18082`  
> OpenAPI / Swagger：`http://127.0.0.1:18082/docs`  
> 统一响应包装：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

业务失败时返回 HTTP 4xx/5xx，`detail` 中为可读错误信息。

---

## 1. 系统

### `GET /health`

健康检查，验证服务与数据库连接。

**响应 data**

| 字段 | 类型 | 说明 |
|---|---|---|
| status | string | `ok` |

---

## 2. Agent 工具注册表

### `GET /tools`

返回本中台对 Agent 暴露的工具清单与权限等级，供 `ToolRegistry` / MCP Adapter 映射。

**权限约定**

| permission | 含义 | Agent 行为 |
|---|---|---|
| `read` | 只读，可直接调用 | 无需用户确认 |
| `write_confirm` | 写操作 | 必须用户确认后调用（`confirmed=true` 或按接口要求） |

**响应 data.tools[]**

| 字段 | 类型 | 说明 |
|---|---|---|
| name | string | Agent 工具名 |
| permission | string | `read` / `write_confirm` |
| description | string | 工具说明 |
| endpoint | string | 中台 HTTP 路径模板 |
| method | string | HTTP 方法 |

---

## 3. 客户

### `GET /customers/{customer_id}/devices`

查询客户名下设备列表。

**路径参数**

| 参数 | 说明 | 示例 |
|---|---|---|
| customer_id | 客户 / sender_id | `u1001` |

**响应 data**

```json
{
  "customer_id": "u1001",
  "devices": [
    {
      "device_id": "DEV-2026-0001",
      "model": "H3C LA2608",
      "category": "网络设备",
      "status": "in_use",
      "warranty_status": "in_warranty",
      "purchase_date": "2026-02-15T00:00:00",
      "cover_url": null
    }
  ]
}
```

### `GET /customers/{customer_id}/tickets`

查询客户售后工单列表。

**响应 data**

```json
{
  "customer_id": "u1001",
  "tickets": [
    {
      "ticket_id": "TKT-2026-000001",
      "device_id": "DEV-2026-0001",
      "model": "H3C LA2608",
      "problem_type": "controller_connection",
      "problem_desc": "LA2608 无法连接无线控制器…",
      "status": "repairing",
      "status_desc": "设备已寄修，维修中心处理中。",
      "priority": "high",
      "created_at": "2026-04-10T10:00:00"
    }
  ]
}
```

---

## 4. 设备

### `GET /devices/{device_id}`

查询设备档案。对应 Agent 工具 `get_device_profile`。

**响应 data**

| 字段 | 类型 | 说明 |
|---|---|---|
| device_id | string | 设备编号 |
| model | string | 型号 |
| serial_number | string | 序列号 |
| category | string | 类别 |
| status | string | 使用状态 |
| purchase_date | datetime | 购买日期 |
| warranty_months | int | 保修月数 |
| warranty_status | string | `in_warranty` / `expired` |
| warranty_deadline | datetime | 保修截止 |
| attributes | object | 规格参数 |
| cover_url | string? | 封面图 |

### `GET /devices/{device_id}/warranty`

查询保修状态。对应 Agent 工具 `check_warranty`。

**响应 data**

| 字段 | 类型 | 说明 |
|---|---|---|
| device_id | string | 设备编号 |
| model | string | 型号 |
| purchase_date | datetime | 购买日期 |
| warranty_months | int | 保修月数 |
| warranty_deadline | datetime | 保修截止日 |
| warranty_status | string | `in_warranty` / `expired` |
| in_warranty | bool | 是否在保 |
| remaining_days | int | 剩余天数（过保为负） |
| status_desc | string | 面向用户的状态说明 |

### `GET /devices/{device_id}/history`

查询设备历史事件。对应 Agent 工具 `get_device_history`。

**响应 data**

```json
{
  "device_id": "DEV-2026-0001",
  "events": [
    {
      "event_time": "2026-03-20T15:30:00",
      "event_type": "config",
      "event_desc": "完成业务 VLAN 与无线控制器地址配置。"
    }
  ]
}
```

---

## 5. 工单

### `GET /tickets/{ticket_id}`

查询工单详情。

### `GET /tickets/{ticket_id}/status`

查询工单状态。对应 Agent 工具 `get_ticket_status`。

**工单状态机**

```text
submitted → accepted → diagnosing → repairing / shipping → completed
                ↘ cancelled
                ↘ transferred
```

| status | 含义 |
|---|---|
| submitted | 已创建，等待受理 |
| accepted | 已受理 |
| diagnosing | 诊断中 |
| repairing | 维修中 |
| shipping | 寄送中 |
| completed | 已完成 |
| cancelled | 已取消 |
| transferred | 已转人工 |

### `GET /tickets/{ticket_id}/repair`

查询维修/寄送进度。对应 Agent 工具 `get_repair_progress`。

**响应 data**

```json
{
  "ticket_id": "TKT-2026-000001",
  "logistics_company": "顺丰速运",
  "tracking_number": "SF-REPAIR-0001",
  "status": "维修中",
  "status_desc": "设备已到达维修中心，工程师处理中。",
  "traces": [
    { "time": "2026-04-12T09:00:00", "desc": "设备已到达维修中心，工程师处理中。" }
  ]
}
```

### `POST /devices/{device_id}/tickets`

创建售后工单。对应 Agent 工具 `create_service_ticket`。**写操作，必须确认。**

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| problem_type | string | 是 | 故障类型，如 `controller_connection` |
| problem_desc | string | 是 | 故障描述 |
| tried_steps | string? | 否 | 已尝试处理步骤 |
| contact_name | string | 否 | 联系人 |
| contact_phone_masked | string | 否 | 脱敏手机 |
| contact_address | string | 否 | 地址 |
| submitted_by | string | 否 | `agent` / `web` / `human` |
| priority | string | 否 | `low`/`normal`/`high`/`urgent` |
| confirmed | bool | **是** | 必须为 `true`，否则 400 |

**错误**

| 状态码 | 场景 |
|---|---|
| 400 | `confirmed != true` |
| 404 | 设备不存在 |
| 409 | 该设备已有进行中的工单 |

**响应 data**

```json
{
  "request_type": "create_service_ticket",
  "request_id": "TKT-2026-000004",
  "device_id": "DEV-2026-0001",
  "ticket_id": "TKT-2026-000004",
  "status": "submitted",
  "status_desc": "工单已创建，等待受理。"
}
```

### `PATCH /tickets/{ticket_id}`

更新工单。对应 Agent 工具 `update_service_ticket`。**写操作。**

**请求体**（均可选）

| 字段 | 说明 |
|---|---|
| status | 新状态 |
| status_desc | 状态说明 |
| tried_steps | 补充处理步骤 |
| priority | 优先级 |
| operator | 操作方 |

### `POST /tickets/{ticket_id}/cancel`

取消工单。对应 Agent 工具 `cancel_service_ticket`。**写操作，必须确认。**

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| reason | string | 否 | 取消原因 |
| operator | string | 否 | 操作方 |
| confirmed | bool | **是** | 必须为 `true` |

---

## 6. 转人工

### `POST /transfers`

创建人工接入记录。对应 Agent 工具 `transfer_to_human`。

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| reason | string | 是 | 转人工原因 |
| customer_id | string | 是 | 客户 ID |
| ticket_id | string? | 否 | 关联工单 |
| submitted_by | string | 否 | 提交来源 |

**响应 data**

```json
{
  "ticket_id": "TKT-2026-000001",
  "status": "transferred",
  "reason": "用户请求人工服务"
}
```

（实际响应为 `OperationResultData`，含 `request_id` / `status` / `status_desc`。）

---

## 7. 知识（对接 shopkeeper_brain RAG）

### `POST /manual/search`

检索设备手册。对应 Agent 工具 `search_manual`。

对接 **shopkeeper_brain**（`E:\AAA message get\shopkeeper_brain`）：

```http
POST {RAG_BASE_URL}/query          # 默认 http://127.0.0.1:8001
Content-Type: application/json

{ "query": "<device_model> <query>", "is_stream": false, "session_id": "可选" }
```

RAG 不可用时返回本地 stub，保证联调。

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| device_model | string | 是 | 设备型号（拼入 RAG query 做消歧） |
| query | string | 是 | 用户问题 |
| top_k | int | 否 | 预留 |
| session_id | string? | 否 | 透传 RAG 会话 ID |
| filters | object? | 否 | 预留 |

**响应 data**

```json
{
  "device_model": "H3C LA2608",
  "query": "怎么配置业务 VLAN？",
  "rag_query": "H3C LA2608 怎么配置业务 VLAN？",
  "answer": "…",
  "citations": [
    {
      "index": 1,
      "source": "local",
      "title": "业务 VLAN 配置",
      "parent_title": "配置指南",
      "file_title": "H3C LA2608室内无线网关 用户手册",
      "item_name": "H3C LA2608",
      "chunk_id": null,
      "url": "",
      "score": 0.92,
      "page": null,
      "snippet": "…"
    }
  ],
  "session_id": "…",
  "source": "rag"
}
```

`source` 为 `rag` 或 `stub`。`citations` 字段对齐 shopkeeper_brain 的 `SourceItem`。

---

## 8. 内部对象约定（前端 / Agent）

前端侧边栏与对话对象使用：

| object.type | id 字段 | 典型 title |
|---|---|---|
| `device` | `device_id` | 设备型号 |
| `ticket` | `ticket_id` | 型号 · 问题类型 |

Chat 网关（预留，由 Agent 项目提供）：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 发送消息 / 对象 |
| GET | `/api/chat/history?sender_id=` | 拉取历史 |

---

## 9. 种子客户与设备（脱敏）

| customer_id | 昵称 | 设备 |
|---|---|---|
| u1001 | 李工 | DEV-2026-0001 H3C LA2608、DEV-2026-0004 H3C S5130 |
| u1002 | 王敏 | DEV-2026-0002 RS PRO RS-12 |
| u1003 | 陈晨 | DEV-2026-0003 华为擎云 L540 |

示例工单：

| ticket_id | 设备 | 状态 |
|---|---|---|
| TKT-2026-000001 | DEV-2026-0001 | repairing |
| TKT-2026-000002 | DEV-2026-0003 | submitted |
| TKT-2026-000003 | DEV-2026-0002 | completed |

> 以上均为脱敏样例与合成工单，不包含真实用户数据。
