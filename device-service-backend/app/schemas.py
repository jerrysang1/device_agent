from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any


# ── 设备 ──────────────────────────────────────────────────────────────


class DeviceSummaryData(BaseModel):
    device_id: str
    model: str
    category: str
    status: str
    warranty_status: str
    purchase_date: datetime
    cover_url: str | None = None


class CustomerDevicesData(BaseModel):
    customer_id: str
    devices: list[DeviceSummaryData]


class DeviceProfileData(BaseModel):
    device_id: str
    model: str
    serial_number: str
    category: str
    status: str
    purchase_date: datetime
    warranty_months: int
    warranty_status: str
    warranty_deadline: datetime
    attributes: dict[str, Any]
    cover_url: str | None = None


class WarrantyData(BaseModel):
    device_id: str
    model: str
    purchase_date: datetime
    warranty_months: int
    warranty_deadline: datetime
    warranty_status: str
    in_warranty: bool
    remaining_days: int
    status_desc: str


class DeviceHistoryData(BaseModel):
    device_id: str
    events: list[dict[str, Any]]


# ── 工单 ──────────────────────────────────────────────────────────────


class TicketSummaryData(BaseModel):
    ticket_id: str
    device_id: str
    model: str
    problem_type: str
    problem_desc: str
    status: str
    status_desc: str
    priority: str
    created_at: datetime


class CustomerTicketsData(BaseModel):
    customer_id: str
    tickets: list[TicketSummaryData]


class TicketDetailData(BaseModel):
    ticket_id: str
    device_id: str
    model: str
    problem_type: str
    problem_desc: str
    tried_steps: str | None = None
    priority: str
    status: str
    status_desc: str
    contact_name: str
    contact_phone_masked: str
    contact_address: str
    created_at: datetime
    updated_at: datetime


class TicketStatusData(BaseModel):
    ticket_id: str
    status: str
    status_desc: str


class RepairTraceData(BaseModel):
    time: datetime
    desc: str


class RepairData(BaseModel):
    ticket_id: str
    logistics_company: str
    tracking_number: str
    status: str
    status_desc: str
    traces: list[RepairTraceData]


class CreateTicketRequest(BaseModel):
    problem_type: str = Field(description="故障类型，如 controller_connection / power_on / screen")
    problem_desc: str = Field(description="故障描述")
    tried_steps: str | None = Field(default=None, description="已尝试的处理步骤")
    contact_name: str = Field(default="用户")
    contact_phone_masked: str = Field(default="138****0000")
    contact_address: str = Field(default="")
    submitted_by: str = Field(default="agent", description="提交来源：agent / web / human")
    priority: Literal["low", "normal", "high", "urgent"] = Field(default="normal")
    confirmed: bool = Field(
        default=False,
        description="高风险写操作必须为 true；Agent 需在用户确认后再带 confirmed=true 调用。",
    )


class UpdateTicketRequest(BaseModel):
    status: str | None = None
    status_desc: str | None = None
    tried_steps: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    operator: str = Field(default="agent")


class CancelTicketRequest(BaseModel):
    reason: str = "用户取消"
    operator: str = Field(default="agent")
    confirmed: bool = Field(default=False)


class TransferToHumanRequest(BaseModel):
    reason: str = Field(description="转人工原因")
    ticket_id: str | None = Field(default=None, description="可选关联工单号")
    customer_id: str = Field(default="u1001")
    submitted_by: str = Field(default="agent")


class ManualSearchRequest(BaseModel):
    device_model: str = Field(description="设备型号，会拼入 RAG query 做型号消歧")
    query: str = Field(description="用户问题 / 故障描述")
    top_k: int = Field(default=5, ge=1, le=20)
    session_id: str | None = Field(default=None, description="可选 RAG 会话 ID")
    filters: dict[str, Any] | None = None


class ManualSearchCitation(BaseModel):
    """对齐 shopkeeper_brain SourceItem，并保留 Agent 友好字段。"""

    index: int = 1
    source: str = Field(default="", description="来源文件名 / local / web_search")
    title: str = ""
    parent_title: str = ""
    file_title: str = ""
    item_name: str = ""
    chunk_id: str | None = None
    url: str = ""
    score: float | None = None
    page: int | None = None
    snippet: str = ""


class ManualSearchResult(BaseModel):
    device_model: str
    query: str
    rag_query: str = Field(default="", description="实际发给 RAG 的 query")
    answer: str
    citations: list[ManualSearchCitation]
    session_id: str | None = None
    source: str = Field(default="stub", description="rag / stub")


class OperationResultData(BaseModel):
    request_type: str
    request_id: str
    device_id: str | None = None
    ticket_id: str | None = None
    status: str
    status_desc: str


class ToolDescriptor(BaseModel):
    name: str
    permission: Literal["read", "write_confirm"]
    description: str
    endpoint: str
    method: str


class ToolsData(BaseModel):
    tools: list[ToolDescriptor]
