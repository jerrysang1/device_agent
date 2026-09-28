from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models import (
    Customer,
    Device,
    DeviceHistory,
    HumanTransfer,
    RepairRecord,
    ServiceTicket,
)
from app.schemas import (
    ApiResponse,
    CancelTicketRequest,
    CreateTicketRequest,
    CustomerDevicesData,
    CustomerTicketsData,
    DeviceHistoryData,
    DeviceProfileData,
    DeviceSummaryData,
    ManualSearchCitation,
    ManualSearchRequest,
    ManualSearchResult,
    OperationResultData,
    RepairData,
    RepairTraceData,
    TicketDetailData,
    TicketStatusData,
    TicketSummaryData,
    ToolDescriptor,
    ToolsData,
    TransferToHumanRequest,
    UpdateTicketRequest,
    WarrantyData,
)


router = APIRouter()

# 只读工具可直接执行；写工具需要用户确认（confirmed=true）
WRITE_TOOLS = {
    "create_service_ticket",
    "update_service_ticket",
    "cancel_service_ticket",
    "transfer_to_human",
}


def _wrap(data):
    return ApiResponse(data=data)


def _get_customer_or_404(db: Session, customer_id: str) -> Customer:
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail=f"客户 {customer_id} 不存在。")
    return customer


def _get_device_or_404(db: Session, device_id: str) -> Device:
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"设备 {device_id} 不存在。")
    return device


def _get_ticket_or_404(db: Session, ticket_id: str) -> ServiceTicket:
    ticket = (
        db.query(ServiceTicket)
        .options(joinedload(ServiceTicket.device), joinedload(ServiceTicket.customer))
        .filter(ServiceTicket.ticket_id == ticket_id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail=f"工单 {ticket_id} 不存在。")
    return ticket


def _warranty_deadline(device: Device) -> datetime:
    return device.purchase_date + timedelta(days=30 * device.warranty_months)


def _warranty_status(device: Device) -> tuple[str, bool, int, str]:
    """返回 (warranty_status, in_warranty, remaining_days, status_desc)。"""
    deadline = _warranty_deadline(device)
    now = datetime.now()
    remaining = (deadline.date() - now.date()).days
    if remaining >= 0:
        return (
            "in_warranty",
            True,
            remaining,
            f"保修中，剩余 {remaining} 天，截止 {deadline:%Y-%m-%d}。",
        )
    return (
        "expired",
        False,
        remaining,
        f"已过保，保修截止日为 {deadline:%Y-%m-%d}。",
    )


def _device_summary(device: Device) -> DeviceSummaryData:
    status, _, _, _ = _warranty_status(device)
    return DeviceSummaryData(
        device_id=device.device_id,
        model=device.model,
        category=device.category,
        status=device.status,
        warranty_status=status,
        purchase_date=device.purchase_date,
        cover_url=device.cover_url,
    )


def _ticket_summary(ticket: ServiceTicket) -> TicketSummaryData:
    return TicketSummaryData(
        ticket_id=ticket.ticket_id,
        device_id=ticket.device.device_id if ticket.device else "",
        model=ticket.device.model if ticket.device else "",
        problem_type=ticket.problem_type,
        problem_desc=ticket.problem_desc[:80],
        status=ticket.status,
        status_desc=ticket.status_desc,
        priority=ticket.priority,
        created_at=ticket.created_at,
    )


def _next_ticket_id(db: Session) -> str:
    """生成工单号（取当前年序最大值 + 1，避免 count() 在删除/并发下重复）。

    步骤：
        1. 查当年前缀下最大 ticket_id 后缀数值。
        2. 序号 +1 后格式化；表上有 ticket_id 唯一约束兜底。

    Args:
        db: SQLAlchemy 会话。

    Returns:
        str: 形如 TKT-2026-000001 的工单号。
    """
    year = datetime.now().year
    prefix = f"TKT-{year}-"
    like = f"{prefix}%"
    latest = (
        db.query(ServiceTicket.ticket_id)
        .filter(ServiceTicket.ticket_id.like(like))
        .order_by(ServiceTicket.ticket_id.desc())
        .first()
    )
    seq = 0
    if latest and latest[0]:
        try:
            seq = int(str(latest[0]).rsplit("-", 1)[-1])
        except ValueError:
            seq = 0
    return f"{prefix}{seq + 1:06d}"


# ── 系统 ──────────────────────────────────────────────────────────────


@router.get(
    "/health",
    response_model=ApiResponse,
    tags=["系统"],
    summary="健康检查",
    description="用于检查服务和数据库连接是否正常。",
)
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return _wrap({"status": "ok"})


@router.get(
    "/tools",
    response_model=ApiResponse,
    tags=["Agent"],
    summary="工具注册表",
    description="返回本中台对 Agent 暴露的工具清单与权限，供 ToolRegistry / MCP Adapter 映射。",
)
def list_tools():
    tools = [
        ToolDescriptor(
            name="search_manual",
            permission="read",
            description="检索设备手册知识，返回 answer + citations。",
            endpoint="POST /manual/search",
            method="POST",
        ),
        ToolDescriptor(
            name="get_device_profile",
            permission="read",
            description="查询设备档案（型号、序列号、购买日期、保修信息）。",
            endpoint="GET /devices/{device_id}",
            method="GET",
        ),
        ToolDescriptor(
            name="check_warranty",
            permission="read",
            description="查询设备保修状态与剩余天数。",
            endpoint="GET /devices/{device_id}/warranty",
            method="GET",
        ),
        ToolDescriptor(
            name="get_device_history",
            permission="read",
            description="查询设备历史事件（巡检、维修、更换）。",
            endpoint="GET /devices/{device_id}/history",
            method="GET",
        ),
        ToolDescriptor(
            name="create_service_ticket",
            permission="write_confirm",
            description="创建售后工单，必须用户确认后带 confirmed=true 调用。",
            endpoint="POST /devices/{device_id}/tickets",
            method="POST",
        ),
        ToolDescriptor(
            name="update_service_ticket",
            permission="write_confirm",
            description="更新工单状态或补充处理步骤。",
            endpoint="PATCH /tickets/{ticket_id}",
            method="PATCH",
        ),
        ToolDescriptor(
            name="cancel_service_ticket",
            permission="write_confirm",
            description="取消工单，必须用户确认。",
            endpoint="POST /tickets/{ticket_id}/cancel",
            method="POST",
        ),
        ToolDescriptor(
            name="transfer_to_human",
            permission="write_confirm",
            description="转人工客服，创建人工接入记录。",
            endpoint="POST /transfers",
            method="POST",
        ),
        ToolDescriptor(
            name="get_ticket_status",
            permission="read",
            description="查询工单当前状态。",
            endpoint="GET /tickets/{ticket_id}/status",
            method="GET",
        ),
        ToolDescriptor(
            name="get_repair_progress",
            permission="read",
            description="查询工单维修/寄送进度。",
            endpoint="GET /tickets/{ticket_id}/repair",
            method="GET",
        ),
    ]
    return _wrap(ToolsData(tools=tools))


# ── 客户 ──────────────────────────────────────────────────────────────


@router.get(
    "/customers/{customer_id}/devices",
    response_model=ApiResponse,
    tags=["客户"],
    summary="查询客户名下设备列表",
    description="根据客户 ID 查询最近设备，用于前端侧边栏展示设备对象。",
)
def customer_devices(customer_id: str, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, customer_id)
    devices = (
        db.query(Device)
        .filter(Device.customer_id == customer.id)
        .order_by(Device.created_at.desc())
        .all()
    )
    return _wrap(
        CustomerDevicesData(
            customer_id=customer.customer_id,
            devices=[_device_summary(d) for d in devices],
        )
    )


@router.get(
    "/customers/{customer_id}/tickets",
    response_model=ApiResponse,
    tags=["客户"],
    summary="查询客户售后工单列表",
    description="根据客户 ID 查询最近售后工单，用于前端侧边栏展示工单对象。",
)
def customer_tickets(customer_id: str, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, customer_id)
    tickets = (
        db.query(ServiceTicket)
        .options(joinedload(ServiceTicket.device))
        .filter(ServiceTicket.customer_id == customer.id)
        .order_by(ServiceTicket.created_at.desc())
        .all()
    )
    return _wrap(
        CustomerTicketsData(
            customer_id=customer.customer_id,
            tickets=[_ticket_summary(t) for t in tickets],
        )
    )


# ── 设备 ──────────────────────────────────────────────────────────────


@router.get(
    "/devices/{device_id}",
    response_model=ApiResponse,
    tags=["设备"],
    summary="查询设备档案",
    description="根据设备编号查询型号、序列号、购买日期、保修信息与规格参数。",
)
def device_profile(device_id: str, db: Session = Depends(get_db)):
    device = _get_device_or_404(db, device_id)
    deadline = _warranty_deadline(device)
    warranty_status, _, _, _ = _warranty_status(device)
    return _wrap(
        DeviceProfileData(
            device_id=device.device_id,
            model=device.model,
            serial_number=device.serial_number,
            category=device.category,
            status=device.status,
            purchase_date=device.purchase_date,
            warranty_months=device.warranty_months,
            warranty_status=warranty_status,
            warranty_deadline=deadline,
            attributes=device.attributes_json or {},
            cover_url=device.cover_url,
        )
    )


@router.get(
    "/devices/{device_id}/warranty",
    response_model=ApiResponse,
    tags=["设备"],
    summary="查询设备保修状态",
    description="计算保修截止日期并返回是否在保、剩余天数。对应 Agent 工具 check_warranty。",
)
def check_warranty(device_id: str, db: Session = Depends(get_db)):
    device = _get_device_or_404(db, device_id)
    deadline = _warranty_deadline(device)
    status, in_warranty, remaining, desc = _warranty_status(device)
    return _wrap(
        WarrantyData(
            device_id=device.device_id,
            model=device.model,
            purchase_date=device.purchase_date,
            warranty_months=device.warranty_months,
            warranty_deadline=deadline,
            warranty_status=status,
            in_warranty=in_warranty,
            remaining_days=remaining,
            status_desc=desc,
        )
    )


@router.get(
    "/devices/{device_id}/history",
    response_model=ApiResponse,
    tags=["设备"],
    summary="查询设备历史事件",
    description="返回巡检、维修、更换等历史事件列表。",
)
def device_history(device_id: str, db: Session = Depends(get_db)):
    device = _get_device_or_404(db, device_id)
    events = (
        db.query(DeviceHistory)
        .filter(DeviceHistory.device_id == device.id)
        .order_by(DeviceHistory.event_time.desc())
        .all()
    )
    return _wrap(
        DeviceHistoryData(
            device_id=device.device_id,
            events=[
                {
                    "event_time": e.event_time,
                    "event_type": e.event_type,
                    "event_desc": e.event_desc,
                }
                for e in events
            ],
        )
    )


# ── 工单 ──────────────────────────────────────────────────────────────


@router.get(
    "/tickets/{ticket_id}",
    response_model=ApiResponse,
    tags=["工单"],
    summary="查询工单详情",
    description="返回工单主信息、设备信息与联系人信息。",
)
def ticket_detail(ticket_id: str, db: Session = Depends(get_db)):
    ticket = _get_ticket_or_404(db, ticket_id)
    return _wrap(
        TicketDetailData(
            ticket_id=ticket.ticket_id,
            device_id=ticket.device.device_id if ticket.device else "",
            model=ticket.device.model if ticket.device else "",
            problem_type=ticket.problem_type,
            problem_desc=ticket.problem_desc,
            tried_steps=ticket.tried_steps,
            priority=ticket.priority,
            status=ticket.status,
            status_desc=ticket.status_desc,
            contact_name=ticket.contact_name,
            contact_phone_masked=ticket.contact_phone_masked,
            contact_address=ticket.contact_address,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )
    )


@router.get(
    "/tickets/{ticket_id}/status",
    response_model=ApiResponse,
    tags=["工单"],
    summary="查询工单状态",
    description="返回工单当前状态及面向用户展示的状态说明。",
)
def ticket_status(ticket_id: str, db: Session = Depends(get_db)):
    ticket = _get_ticket_or_404(db, ticket_id)
    return _wrap(
        TicketStatusData(
            ticket_id=ticket.ticket_id,
            status=ticket.status,
            status_desc=ticket.status_desc,
        )
    )


@router.get(
    "/tickets/{ticket_id}/repair",
    response_model=ApiResponse,
    tags=["工单"],
    summary="查询维修/寄送进度",
    description="返回寄修物流、维修状态和进度轨迹。对应 Agent 工具 get_repair_progress。",
)
def ticket_repair(ticket_id: str, db: Session = Depends(get_db)):
    ticket = _get_ticket_or_404(db, ticket_id)
    record = (
        db.query(RepairRecord)
        .options(joinedload(RepairRecord.traces))
        .filter(RepairRecord.ticket_id == ticket.id)
        .order_by(RepairRecord.updated_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"工单 {ticket_id} 暂无维修/寄送信息。")

    traces = sorted(record.traces, key=lambda item: item.trace_time, reverse=True)
    return _wrap(
        RepairData(
            ticket_id=ticket.ticket_id,
            logistics_company=record.logistics_company,
            tracking_number=record.tracking_number,
            status=record.status,
            status_desc=record.status_desc,
            traces=[
                RepairTraceData(time=trace.trace_time, desc=trace.trace_desc) for trace in traces
            ],
        )
    )


@router.post(
    "/devices/{device_id}/tickets",
    response_model=ApiResponse,
    tags=["工单"],
    summary="创建售后工单",
    description=(
        "为指定设备创建售后工单。属于写操作，必须带 confirmed=true。"
        "同一设备已有进行中的工单时返回 409。"
    ),
)
def create_service_ticket(
    device_id: str,
    body: CreateTicketRequest,
    db: Session = Depends(get_db),
):
    if not body.confirmed:
        raise HTTPException(
            status_code=400,
            detail="创建工单属于高风险写操作，必须在用户确认后携带 confirmed=true 调用。",
        )

    device = _get_device_or_404(db, device_id)

    existing = (
        db.query(ServiceTicket)
        .filter(
            ServiceTicket.device_id == device.id,
            ServiceTicket.status.in_(["submitted", "accepted", "diagnosing", "repairing", "shipping"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"设备 {device_id} 已存在进行中的工单 {existing.ticket_id}。",
        )

    ticket_id = _next_ticket_id(db)
    now = datetime.now()
    ticket = ServiceTicket(
        ticket_id=ticket_id,
        device_id=device.id,
        customer_id=device.customer_id,
        problem_type=body.problem_type,
        problem_desc=body.problem_desc,
        tried_steps=body.tried_steps,
        priority=body.priority,
        status="submitted",
        status_desc="工单已创建，等待受理。",
        contact_name=body.contact_name,
        contact_phone_masked=body.contact_phone_masked,
        contact_address=body.contact_address,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.commit()

    return _wrap(
        OperationResultData(
            request_type="create_service_ticket",
            request_id=ticket_id,
            device_id=device.device_id,
            ticket_id=ticket_id,
            status="submitted",
            status_desc=ticket.status_desc,
        )
    )


@router.patch(
    "/tickets/{ticket_id}",
    response_model=ApiResponse,
    tags=["工单"],
    summary="更新工单",
    description="更新工单状态、优先级或补充处理步骤。属于写操作。",
)
def update_service_ticket(
    ticket_id: str,
    body: UpdateTicketRequest,
    db: Session = Depends(get_db),
):
    ticket = _get_ticket_or_404(db, ticket_id)

    if ticket.status in {"completed", "cancelled"}:
        raise HTTPException(
            status_code=400,
            detail=f"工单 {ticket_id} 已处于终态（{ticket.status}），不可再更新。",
        )

    if body.status is not None:
        ticket.status = body.status
    if body.status_desc is not None:
        ticket.status_desc = body.status_desc
    if body.tried_steps is not None:
        ticket.tried_steps = body.tried_steps
    if body.priority is not None:
        ticket.priority = body.priority
    ticket.updated_at = datetime.now()
    db.commit()

    return _wrap(
        OperationResultData(
            request_type="update_service_ticket",
            request_id=ticket.ticket_id,
            device_id=ticket.device.device_id if ticket.device else None,
            ticket_id=ticket.ticket_id,
            status=ticket.status,
            status_desc=ticket.status_desc,
        )
    )


@router.post(
    "/tickets/{ticket_id}/cancel",
    response_model=ApiResponse,
    tags=["工单"],
    summary="取消工单",
    description="取消售后工单。属于写操作，必须用户确认后带 confirmed=true。",
)
def cancel_service_ticket(
    ticket_id: str,
    body: CancelTicketRequest,
    db: Session = Depends(get_db),
):
    if not body.confirmed:
        raise HTTPException(
            status_code=400,
            detail="取消工单属于高风险写操作，必须在用户确认后携带 confirmed=true 调用。",
        )

    ticket = _get_ticket_or_404(db, ticket_id)
    if ticket.status in {"completed", "cancelled"}:
        raise HTTPException(
            status_code=400,
            detail=f"工单 {ticket_id} 已处于终态，无法取消。",
        )

    ticket.status = "cancelled"
    ticket.status_desc = f"工单已取消：{body.reason}"
    ticket.updated_at = datetime.now()
    db.commit()

    return _wrap(
        OperationResultData(
            request_type="cancel_service_ticket",
            request_id=ticket.ticket_id,
            ticket_id=ticket.ticket_id,
            status="cancelled",
            status_desc=ticket.status_desc,
        )
    )


# ── 转人工 ────────────────────────────────────────────────────────────


@router.post(
    "/transfers",
    response_model=ApiResponse,
    tags=["转人工"],
    summary="转人工客服",
    description=(
        "创建人工接入记录。返回 ticket_id/status/reason，"
        "status=transferred。可关联已有工单，也可仅基于客户会话转接。"
    ),
)
def transfer_to_human(body: TransferToHumanRequest, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, body.customer_id)

    ticket_pk = None
    related_ticket_id = body.ticket_id
    if body.ticket_id:
        ticket = _get_ticket_or_404(db, body.ticket_id)
        ticket_pk = ticket.id
        if ticket.status not in {"completed", "cancelled"}:
            ticket.status = "transferred"
            ticket.status_desc = f"已转人工：{body.reason}"
            ticket.updated_at = datetime.now()
    else:
        related_ticket_id = None

    transfer_id = f"HUM-{datetime.now():%Y%m%d%H%M%S}{uuid4().hex[:4].upper()}"
    transfer = HumanTransfer(
        transfer_id=transfer_id,
        ticket_id=ticket_pk,
        customer_id=customer.id,
        reason=body.reason,
        status="transferred",
        status_desc="已转接人工客服，请稍候。",
        created_at=datetime.now(),
    )
    db.add(transfer)
    db.commit()

    return _wrap(
        OperationResultData(
            request_type="transfer_to_human",
            request_id=transfer_id,
            ticket_id=related_ticket_id,
            status="transferred",
            status_desc="已转接人工客服，请稍候。",
        )
    )


# ── 手册知识（对接 shopkeeper_brain RAG） ─────────────────────────────


def _build_rag_query(device_model: str, query: str) -> str:
    """把型号拼进 query，帮助 RAG 做商品名消歧。"""
    model = (device_model or "").strip()
    text = (query or "").strip()
    if not model or model in text:
        return text
    return f"{model} {text}"


def _map_rag_citations(sources: list) -> list[ManualSearchCitation]:
    citations: list[ManualSearchCitation] = []
    for i, item in enumerate(sources or [], start=1):
        if not isinstance(item, dict):
            continue
        file_title = item.get("file_title") or ""
        title = item.get("title") or ""
        citations.append(
            ManualSearchCitation(
                index=item.get("index") or i,
                source=item.get("source") or file_title or "local",
                title=title,
                parent_title=item.get("parent_title") or "",
                file_title=file_title,
                item_name=item.get("item_name") or "",
                chunk_id=item.get("chunk_id"),
                url=item.get("url") or "",
                score=item.get("score"),
                page=item.get("page"),
                snippet=item.get("snippet") or "",
            )
        )
    return citations


@router.post(
    "/manual/search",
    response_model=ApiResponse,
    tags=["知识"],
    summary="检索设备手册",
    description=(
        "Agent 工具 search_manual 的 HTTP 入口。"
        "对接 shopkeeper_brain：POST {RAG_BASE_URL}/query（非流式），"
        "将 sources 映射为 citations。RAG 不可用时回退本地 stub。"
    ),
)
async def search_manual(body: ManualSearchRequest, db: Session = Depends(get_db)):
    model_exists = (
        db.query(Device).filter(Device.model.ilike(f"%{body.device_model}%")).first() is not None
    )
    rag_query = _build_rag_query(body.device_model, body.query)

    rag_url = (settings.rag_base_url or "").rstrip("/")
    if rag_url:
        try:
            async with httpx.AsyncClient(timeout=settings.rag_timeout_seconds) as client:
                # shopkeeper_brain 契约：POST /query，is_stream=false 同步返回 answer + sources
                payload: dict = {
                    "query": rag_query,
                    "is_stream": False,
                }
                if body.session_id:
                    payload["session_id"] = body.session_id

                resp = await client.post(f"{rag_url}/query", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    # 兼容扁平返回与 {data: ...} 包装
                    if isinstance(data, dict) and "answer" not in data and isinstance(data.get("data"), dict):
                        data = data["data"]
                    answer = data.get("answer") or ""
                    sources = data.get("sources") or data.get("citations") or []
                    return _wrap(
                        ManualSearchResult(
                            device_model=body.device_model,
                            query=body.query,
                            rag_query=rag_query,
                            answer=answer,
                            citations=_map_rag_citations(sources),
                            session_id=data.get("session_id"),
                            source="rag",
                        )
                    )
        except Exception:
            # RAG 不可用时回退 stub，保证 Agent 链路可继续演示
            pass

    # 本地 stub：保证无 RAG 时接口仍可联调
    answer = (
        f"【本地手册摘要·{body.device_model}】关于「{body.query}」："
        "请先检查电源与物理连接，再确认固件版本与配置下发。"
        "若涉及无线控制器接入，请核对 AC 地址、AP 上线状态与业务 VLAN 是否放行。"
    )
    if not model_exists:
        answer = f"未在设备目录中找到型号「{body.device_model}」的匹配记录。" + answer

    return _wrap(
        ManualSearchResult(
            device_model=body.device_model,
            query=body.query,
            rag_query=rag_query,
            answer=answer,
            citations=[
                ManualSearchCitation(
                    index=1,
                    source=f"{body.device_model}-用户手册",
                    file_title=f"{body.device_model}-用户手册",
                    title="故障排查",
                    snippet="检查物理连接与业务 VLAN 配置。",
                    page=12,
                )
            ],
            source="stub",
        )
    )
