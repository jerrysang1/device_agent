"""中台工具注册表：固定端点、类型化结果，不接受 YAML/模型指定任意 URL。

设计要点：
    1. action 名与 flow_config 里 call_tool.action 一一对应。
    2. 只做 HTTP 调用与字段归一，业务决策在 FlowExecutor。
    3. 读/写权限字段保留在结果里，供执行器与审计使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class _CallToolLike(Protocol):
    """call_tool 步骤的最小结构（避免与 models 循环 import）。"""

    action: str
    permission: str
    params: dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    """一次工具调用的结果。

    Attributes:
        ok: 是否成功。
        data: 归一后的业务字段，供 ${tool.xxx} 模板使用。
        error: 失败时的可读原因（不暴露堆栈）。
        http_status: 原始 HTTP 状态，便于日志；未知为 0。
    """

    ok: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    http_status: int = 0


class ToolRegistry:
    """按 action 名分发到中台固定接口。"""

    def __init__(self, device_client: Any) -> None:
        """注入中台客户端（真实 http_client 或测试替身）。

        Args:
            device_client: 需实现 get_json / post_json。
        """
        self.device_client = device_client

    async def call(self, step: _CallToolLike, params: dict[str, Any]) -> ToolResult:
        """执行一个 call_tool 步骤。

        步骤：
            1. 按 action 查处理器；未知 action 直接失败。
            2. 调中台，兼容 {data: ...} 包装。
            3. 异常归一成 ToolResult.error，不抛给上层。

        Args:
            step: 工具步骤（含 action / permission）。
            params: 已渲染好的入参。

        Returns:
            ToolResult: 类型化结果。
        """
        # 1. 白名单分发，禁止 YAML 写任意 action
        handler = _ACTIONS.get(step.action)
        if handler is None:
            return ToolResult(ok=False, error=f"未知工具: {step.action}")
        # 2/3. 异常收成可读错误，不让 5xx 堆栈漏到前端
        try:
            return await handler(self.device_client, params)
        except Exception as exc:
            return ToolResult(ok=False, error=_readable_error(exc, step.action))


def _readable_error(exc: Exception, action: str) -> str:
    """把异常收成用户可读、日志可查的一句话。

    Args:
        exc: 原始异常。
        action: 工具名。

    Returns:
        str: 可读错误。
    """
    message = str(exc)
    if "404" in message or "不存在" in message:
        return f"{action}: 目标资源不存在"
    if "502" in message or "503" in message or "500" in message:
        return f"{action}: 中台暂时不可用"
    if "timeout" in message.lower() or "超时" in message:
        return f"{action}: 调用超时"
    return f"{action}: 调用失败"


def _unwrap(payload: Any) -> dict[str, Any]:
    """去掉 {code,message,data} 包装，只要业务字典。

    Args:
        payload: 接口原始返回。

    Returns:
        dict: 业务字段。
    """
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


async def _owned_device_ids(client: Any, customer_id: str) -> set[str]:
    """拉取客户名下设备编号集合，用于归属校验。

    Args:
        client: 中台客户端。
        customer_id: 演示环境即 sender_id，如 u1001。

    Returns:
        set[str]: 归属该客户的 device_id 集合。
    """
    payload = await client.get_json(f"/customers/{customer_id}/devices")
    data = _unwrap(payload)
    devices = data.get("devices") or []
    result: set[str] = set()
    for item in devices:
        if isinstance(item, dict) and item.get("device_id"):
            result.add(str(item["device_id"]))
    return result


async def _ensure_device_owned(client: Any, customer_id: str, device_id: str) -> ToolResult | None:
    """校验设备归属；未通过返回失败 ToolResult，通过返回 None。"""
    if not customer_id:
        return None  # 未注入身份时跳过（兼容无会话的单测）
    try:
        owned = await _owned_device_ids(client, customer_id)
    except Exception:
        return ToolResult(ok=False, error="无法校验设备归属，请稍后重试")
    if device_id not in owned:
        return ToolResult(ok=False, error="设备不属于当前用户")
    return None


async def _check_warranty(client: Any, params: dict[str, Any]) -> ToolResult:
    """查保修：GET /devices/{device_id}/warranty（先归属校验）。

    步骤：
        1. 校验 device_id 入参。
        2. 归属校验：设备必须在当前用户名下。
        3. 调中台查保修并归一字段（含中文状态）。

    Args:
        client: 中台客户端。
        params: 渲染后的入参（含 customer_id / device_id）。

    Returns:
        ToolResult: 成功带归一字段；失败带可读 error。
    """
    # 1. 入参
    device_id = str(params.get("device_id") or "")
    if not device_id:
        return ToolResult(ok=False, error="check_warranty: 缺少 device_id")
    # 2. 为什么先归属：中台 warranty 接口本身不校验客户，Agent 必须挡一层
    denied = await _ensure_device_owned(client, str(params.get("customer_id") or ""), device_id)
    if denied is not None:
        return denied
    # 3. 查询 + 字段归一
    payload = await client.get_json(f"/devices/{device_id}/warranty")
    data = _unwrap(payload)
    normalized = {
        "device_id": str(data.get("device_id") or device_id),
        "warranty_status_code": str(data.get("warranty_status") or data.get("status") or "unknown"),
        "warranty_deadline": str(
            data.get("warranty_deadline") or data.get("warranty_until") or "—"
        ),
        "model": str(data.get("model") or device_id),
    }
    # 为什么：YAML 模板 ${tool.warranty_status} 面向用户，给中文
    code = normalized["warranty_status_code"]
    normalized["warranty_status"] = {
        "in_warranty": "在保修期内",
        "expired": "已过保",
    }.get(code, code)
    return ToolResult(ok=True, data=normalized)


async def _get_repair_progress(client: Any, params: dict[str, Any]) -> ToolResult:
    """查维修进度：GET /tickets/{ticket_id}/repair（先归属校验）。"""
    ticket_id = str(params.get("ticket_id") or "")
    if not ticket_id:
        return ToolResult(ok=False, error="get_repair_progress: 缺少 ticket_id")
    customer_id = str(params.get("customer_id") or "")
    if customer_id:
        try:
            tickets = await client.get_json(f"/customers/{customer_id}/tickets")
            data = _unwrap(tickets)
            ids = {
                str(t.get("ticket_id"))
                for t in (data.get("tickets") or [])
                if isinstance(t, dict) and t.get("ticket_id")
            }
            if ticket_id not in ids:
                return ToolResult(ok=False, error="工单不属于当前用户")
        except Exception:
            return ToolResult(ok=False, error="无法校验工单归属，请稍后重试")
    payload = await client.get_json(f"/tickets/{ticket_id}/repair")
    data = _unwrap(payload)
    normalized = {
        "ticket_id": str(data.get("ticket_id") or ticket_id),
        "status_desc": str(data.get("status_desc") or data.get("status") or "处理中"),
        "logistics_tip": str(data.get("logistics_tip") or ""),
    }
    return ToolResult(ok=True, data=normalized)


async def _create_service_ticket(client: Any, params: dict[str, Any]) -> ToolResult:
    """建单：POST /devices/{device_id}/tickets（先归属校验；确认令牌仍属 P1）。"""
    device_id = str(params.get("device_id") or "")
    if not device_id:
        return ToolResult(ok=False, error="create_service_ticket: 缺少 device_id")
    denied = await _ensure_device_owned(client, str(params.get("customer_id") or ""), device_id)
    if denied is not None:
        return denied
    body = dict(params)
    body.pop("customer_id", None)  # 不把演示身份当业务入参强行写入
    payload = await client.post_json(f"/devices/{device_id}/tickets", body)
    data = _unwrap(payload)
    return ToolResult(
        ok=True,
        data={
            "ticket_id": str(data.get("ticket_id") or ""),
            "status_desc": str(data.get("status_desc") or data.get("status") or "已创建"),
        },
    )


async def _transfer_to_human(client: Any, params: dict[str, Any]) -> ToolResult:
    """转人工：POST /transfers。"""
    payload = await client.post_json("/transfers", dict(params))
    data = _unwrap(payload)
    return ToolResult(
        ok=True,
        data={
            "status_desc": str(data.get("status_desc") or "已转人工"),
            "ticket_id": str(data.get("ticket_id") or ""),
        },
    )


_ACTIONS = {
    "check_warranty": _check_warranty,
    "get_repair_progress": _get_repair_progress,
    "create_service_ticket": _create_service_ticket,
    "transfer_to_human": _transfer_to_human,
}

# 对外白名单：YAML call_tool.action 必须落在此集合（models 加载期校验）
KNOWN_TOOL_ACTIONS: frozenset[str] = frozenset(_ACTIONS)
