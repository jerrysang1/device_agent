"""DialogueService ↔ FlowExecutor 集成：持久化状态是否真正驱动多轮。

不是孤立模型测试：走 service.chat，用内存仓储模拟 load/save。
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from agent_gateway.domain.state import DialogueState
from agent_gateway.service.dialogue_service import DialogueService


class FakeRepo:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, list[dict[str, Any]]] = {}

    def load_state(self, sender_id: str) -> Optional[dict[str, Any]]:
        return self.store.get(sender_id)

    def save_state(self, sender_id: str, data: dict[str, Any]) -> None:
        self.store[sender_id] = data

    def append_messages(self, sender_id: str, messages: list[dict[str, Any]]) -> None:
        self.messages.setdefault(sender_id, []).extend(messages)

    def list_messages(self, sender_id: str) -> list[dict[str, Any]]:
        return list(self.messages.get(sender_id, []))


class FakeDevice:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        if path.startswith("/customers/") and path.endswith("/devices"):
            return {
                "code": 0,
                "data": {"customer_id": "u1001", "devices": [{"device_id": "DEV-2026-0001"}]},
            }
        return {
            "code": 0,
            "data": {
                "device_id": "DEV-2026-0001",
                "warranty_status": "in_warranty",
                "warranty_deadline": "2027-02-15",
            },
        }

    async def post_json(self, path: str, json_body: Any = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        return {"code": 0, "data": {"ticket_id": "TKT-2026-000001"}}


def test_dialogue_service_multi_turn_uses_persisted_state() -> None:
    """第一轮存 step_id，第二轮从仓储还原后继续收槽——证明 state 真被 FlowExecutor 吃进。"""
    repo, device = FakeRepo(), FakeDevice()
    service = DialogueService(repository=repo, device_client=device)

    first = asyncio.run(service.chat("u1001", "帮我查保修"))
    assert any("设备编号" in m.get("text", "") for m in first["messages"])
    assert device.calls == []
    # 状态已落库且含任务
    saved = repo.store["u1001"]
    assert saved.get("task") and saved["task"].get("flow_id") == "check_warranty"

    second = asyncio.run(service.chat("u1001", "DEV-2026-0001"))
    text = " ".join(m.get("text", "") for m in second["messages"])
    assert "DEV-2026-0001" in text
    assert "/devices/DEV-2026-0001/warranty" in device.calls
    # 流程结束后 task 应清掉
    assert repo.store["u1001"].get("task") in (None, {})


def test_dialogue_service_state_roundtrip_object() -> None:
    """load 出的是 DialogueState 实例，且能 from_dict 还原任务字段。"""
    repo, device = FakeRepo(), FakeDevice()
    service = DialogueService(repository=repo, device_client=device)
    asyncio.run(service.chat("u1001", "查保修"))
    data = repo.load_state("u1001")
    state = DialogueState.from_dict(data or {})
    assert state.task is not None
    assert state.task.flow_id == "check_warranty"
    assert state.task.step_id == "ask_device_id"
