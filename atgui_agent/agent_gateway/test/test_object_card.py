"""对象卡片管道测试：API 放行 object-only，收槽填编号，无任务写入 focused_object。"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from agent_gateway.domain.state import DialogueState
from agent_gateway.engine.stub_brain import handle_message


class FakeDeviceClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.responses: dict[str, Any] = {}

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        if path.startswith("/customers/") and path.endswith("/devices"):
            return {
                "code": 0,
                "data": {
                    "customer_id": "u1001",
                    "devices": [{"device_id": "DEV-2026-0001"}, {"device_id": "DEV-2026-0004"}],
                },
            }
        for key, value in self.responses.items():
            if key in path:
                return value
        raise RuntimeError(f"请求 GET {path} 返回 HTTP 404：设备不存在")

    async def post_json(self, path: str, json_body: Any = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        return {"code": 0, "data": {"ticket_id": "TKT-2026-000009", "status_desc": "已转人工"}}


DEVICE_CARD = {
    "type": "device",
    "id": "DEV-2026-0001",
    "title": "H3C LA2608",
    "attributes": {
        "device_id": "DEV-2026-0001",
        "model": "H3C LA2608",
        "warranty_status": "in_warranty",
    },
}


def test_object_fills_device_slot_during_warranty() -> None:
    """收槽中点设备卡片：直接填 device_id 并查保修，不要求再打编号。"""
    client = FakeDeviceClient()
    client.responses["DEV-2026-0001"] = {
        "code": 0,
        "data": {
            "device_id": "DEV-2026-0001",
            "warranty_status": "in_warranty",
            "warranty_deadline": "2027-02-15",
            "model": "H3C LA2608",
        },
    }
    state = DialogueState(sender_id="u1001")
    asyncio.run(handle_message("查保修", "u1001", client, state=state))
    assert state.task is not None

    result = asyncio.run(handle_message("", "u1001", client, state=state, user_object=DEVICE_CARD))
    text = " ".join(m.text for m in result.messages)
    assert "DEV-2026-0001" in text
    assert any("warranty" in c for c in client.calls)
    assert state.task is None


def test_object_without_task_sets_focused_object() -> None:
    """无任务时点卡片：写入 focused_object 并给意图引导。"""
    client = FakeDeviceClient()
    state = DialogueState(sender_id="u1001")
    result = asyncio.run(handle_message("", "u1001", client, state=state, user_object=DEVICE_CARD))
    text = " ".join(m.text for m in result.messages)
    assert "已选中" in text and "DEV-2026-0001" in text
    assert state.focused_object is not None
    assert state.focused_object.id == "DEV-2026-0001"
    assert state.task is None
    assert client.calls == []


class FakeStateRepository:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.messages: dict[str, list] = {}

    def load_state(self, sender_id: str) -> Optional[dict[str, Any]]:
        return self.store.get(sender_id)

    def save_state(self, sender_id: str, data: dict[str, Any]) -> None:
        self.store[sender_id] = data

    def append_messages(self, sender_id: str, messages: list) -> None:
        self.messages.setdefault(sender_id, []).extend(messages)

    def list_messages(self, sender_id: str) -> list:
        return list(self.messages.get(sender_id, []))


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeDeviceClient]:
    fake_repo = FakeStateRepository()
    fake_device = FakeDeviceClient()
    fake_device.responses["DEV-2026-0001"] = {
        "code": 0,
        "data": {
            "device_id": "DEV-2026-0001",
            "warranty_status": "in_warranty",
            "warranty_deadline": "2027-02-15",
        },
    }

    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    import agent_gateway.api.app as app_module
    import agent_gateway.infrastructure.database as db_module
    import agent_gateway.infrastructure.http_client as http_module

    monkeypatch.setattr(db_module, "init_database", _noop)
    monkeypatch.setattr(db_module, "close_database", _noop)
    monkeypatch.setattr(http_module, "close_http_client", _noop)
    monkeypatch.setattr(app_module, "init_database", _noop)
    monkeypatch.setattr(app_module, "close_database", _noop)
    monkeypatch.setattr(app_module, "close_http_client", _noop)

    from agent_gateway.api.app import create_app
    from agent_gateway.api.dependencies import get_device_client, get_state_repository

    app = create_app()
    app.dependency_overrides[get_state_repository] = lambda: fake_repo
    app.dependency_overrides[get_device_client] = lambda: fake_device
    return TestClient(app), fake_device


def test_api_chat_accepts_object_only(api_client: tuple[TestClient, FakeDeviceClient]) -> None:
    """POST /api/chat 仅带 object 时应 200，并引导下一步意图。"""
    http, _device = api_client
    resp = http.post("/api/chat", json={"sender_id": "u1001", "object": DEVICE_CARD})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["messages"]
    joined = " ".join(m.get("text", "") for m in payload["messages"])
    assert "已选中" in joined
    history = http.get("/api/chat/history", params={"sender_id": "u1001"})
    types = [m.get("type") for m in history.json().get("messages", [])]
    assert "object" in types


def test_api_chat_still_rejects_empty(api_client: tuple[TestClient, FakeDeviceClient]) -> None:
    http, _device = api_client
    resp = http.post("/api/chat", json={"sender_id": "u1001", "text": "  "})
    assert resp.status_code == 400
