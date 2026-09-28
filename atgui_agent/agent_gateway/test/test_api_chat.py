"""Agent 网关最小闭环 API 测试。

不依赖真实 MySQL / LLM / RAG：仓储与中台客户端用替身。

覆盖：
    1. GET /health
    2. 保修查询正常路径
    3. 缺少设备编号 → 追问
    4. 未知设备 → 明确错误
    5. 中台 5xx → 降级提示
    6. 未知意图 → 能力说明
    7. 历史读取
"""

from __future__ import annotations

from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------
class FakeStateRepository:
    """内存仓储：测试用，不连数据库。"""

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


class FakeDeviceClient:
    """中台替身：按 device_id 返回预设结果。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.responses: dict[str, Any] = {}
        self.raise_5xx = False

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        if self.raise_5xx:
            raise RuntimeError("请求 GET /devices/xxx 返回 HTTP 502：bad gateway")
        if path.startswith("/customers/") and path.endswith("/devices"):
            # 归属校验：u1001 名下两台设备
            return {
                "code": 0,
                "data": {
                    "customer_id": "u1001",
                    "devices": [
                        {"device_id": "DEV-2026-0001"},
                        {"device_id": "DEV-2026-0004"},
                    ],
                },
            }
        for key, value in self.responses.items():
            if key in path:
                return value
        raise RuntimeError(f"请求 GET {path} 返回 HTTP 404：设备不存在")

    async def post_json(self, path: str, json_body: Any = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        return {"code": 0, "data": {"ticket_id": "TKT-2026-000009"}}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeDeviceClient]:
    """构造 TestClient，并注入替身仓储与中台客户端。"""
    fake_repo = FakeStateRepository()
    fake_device = FakeDeviceClient()

    # 测试不连真实数据库/HTTP：拦掉 lifespan 里的资源初始化
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
    # FastAPI 标准做法：依赖覆盖（Depends 已绑定原函数，monkeypatch 换不掉）
    app.dependency_overrides[get_state_repository] = lambda: fake_repo
    app.dependency_overrides[get_device_client] = lambda: fake_device
    return TestClient(app), fake_device


def test_health(client: tuple[TestClient, FakeDeviceClient]) -> None:
    """GET /health 应返回 ok。"""
    http, _ = client
    resp = http.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"


def test_warranty_query_ok(client: tuple[TestClient, FakeDeviceClient]) -> None:
    """识别设备编号并调用中台一次，回复来自中台数据。"""
    http, device = client
    device.responses["DEV-2026-0001"] = {
        "code": 0,
        "data": {"device_id": "DEV-2026-0001", "warranty_status": "in_warranty", "warranty_until": "2027-02-15"},
    }
    resp = http.post("/api/chat", json={"sender_id": "u1001", "text": "DEV-2026-0001 还在保修吗？"})
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) >= 1
    text = " ".join(m.get("text", "") for m in messages)
    assert "DEV-2026-0001" in text
    assert "/devices/DEV-2026-0001/warranty" in device.calls
    assert "in_warranty" in text or "保修" in text


def test_warranty_missing_device_id(client: tuple[TestClient, FakeDeviceClient]) -> None:
    """提到保修但没有设备编号 → 追问，不调中台。"""
    http, device = client
    resp = http.post("/api/chat", json={"sender_id": "u1001", "text": "帮我查一下保修"})
    assert resp.status_code == 200
    text = " ".join(m.get("text", "") for m in resp.json()["messages"])
    assert "设备编号" in text or "DEV-" in text
    assert device.calls == []


def test_warranty_unknown_device(client: tuple[TestClient, FakeDeviceClient]) -> None:
    """设备不存在 → 明确错误，不伪造保修结果。"""
    http, device = client
    resp = http.post("/api/chat", json={"sender_id": "u1001", "text": "DEV-9999-9999 在保修期吗"})
    assert resp.status_code == 200
    text = " ".join(m.get("text", "") for m in resp.json()["messages"])
    assert "不存在" in text or "未找到" in text or "失败" in text or "不属于" in text
    assert "in_warranty" not in text
    assert "有效期" not in text


def test_warranty_tool_5xx(client: tuple[TestClient, FakeDeviceClient]) -> None:
    """中台故障 → 降级提示，不吞错。"""
    http, device = client
    device.raise_5xx = True
    resp = http.post("/api/chat", json={"sender_id": "u1001", "text": "DEV-2026-0001 保修状态"})
    assert resp.status_code == 200
    text = " ".join(m.get("text", "") for m in resp.json()["messages"])
    assert "失败" in text or "稍后" in text or "无法" in text


def test_unknown_intent(client: tuple[TestClient, FakeDeviceClient]) -> None:
    """未知意图 → 能力说明，不乱调工具。"""
    http, device = client
    resp = http.post("/api/chat", json={"sender_id": "u1001", "text": "今天天气怎么样"})
    assert resp.status_code == 200
    text = " ".join(m.get("text", "") for m in resp.json()["messages"])
    assert "保修" in text or "报修" in text or "转人工" in text
    assert device.calls == []


def test_history_persisted(client: tuple[TestClient, FakeDeviceClient]) -> None:
    """对话后可从 history 读回用户与机器人消息。"""
    http, device = client
    device.responses["DEV-2026-0001"] = {"code": 0, "data": {"device_id": "DEV-2026-0001", "warranty_status": "in_warranty", "warranty_until": "2027-02-15"}}
    http.post("/api/chat", json={"sender_id": "u1001", "text": "DEV-2026-0001 还在保修吗？"})
    resp = http.get("/api/chat/history", params={"sender_id": "u1001"})
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert any(m.get("role") == "user" for m in messages)
    assert any(m.get("role") == "bot" for m in messages)
