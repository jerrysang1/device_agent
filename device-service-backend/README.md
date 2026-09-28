# device-service-backend

设备维修中台业务服务，为 DeviceCare Agent 提供设备、保修、工单与转人工等确定性业务能力。

> 评测与演示数据由脱敏设备样例、合成工单记录和人工设计的对话场景组成，不包含真实用户数据。

## 提供能力

- 客户名下设备 / 工单列表
- 设备档案与保修查询
- 设备历史事件
- 售后工单创建 / 更新 / 取消
- 维修寄送进度
- 转人工
- 手册检索（预留 RAG 对接，本地 stub 可联调）
- Agent 工具注册表 `GET /tools`

## 启动方式

推荐 Docker Compose（见上层目录）：

```powershell
cd ..\device_agent\atgui_agent
docker compose up --build
```

本地开发：

```powershell
cd device-service-backend
uv sync
uv run uvicorn app.app:app --reload --port 18082
```

环境变量见 `.env.example`。

## 核心接口

- `GET /health`
- `GET /tools`
- `GET /customers/{customer_id}/devices`
- `GET /customers/{customer_id}/tickets`
- `GET /devices/{device_id}`
- `GET /devices/{device_id}/warranty`
- `GET /devices/{device_id}/history`
- `GET /tickets/{ticket_id}`
- `GET /tickets/{ticket_id}/status`
- `GET /tickets/{ticket_id}/repair`
- `POST /devices/{device_id}/tickets`
- `PATCH /tickets/{ticket_id}`
- `POST /tickets/{ticket_id}/cancel`
- `POST /transfers`
- `POST /manual/search`

启动后默认地址：

- API: `http://127.0.0.1:18082`
- OpenAPI: `http://127.0.0.1:18082/docs`
