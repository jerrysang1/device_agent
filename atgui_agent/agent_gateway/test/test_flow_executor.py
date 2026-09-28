"""YAML 流程执行器测试：多轮收槽 → 调工具 → 模板回复。

不依赖真实 MySQL / LLM / RAG；中台用替身。
用 asyncio.run 驱动协程，避免额外 pytest 插件依赖。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_gateway.domain.state import DialogueState
from agent_gateway.engine.flow_executor import FlowExecutor
from agent_gateway.task.tools import ToolRegistry


class FakeDeviceClient:
    """中台替身：记录调用路径；默认 u1001 只拥有 0001/0004。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.responses: dict[str, Any] = {}
        self.raise_5xx = False
        self.owned_devices = {"DEV-2026-0001", "DEV-2026-0004"}
        self.owned_tickets = {"TKT-2026-000001"}

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        if self.raise_5xx:
            raise RuntimeError("请求 GET /devices/xxx 返回 HTTP 502：bad gateway")
        if path.endswith("/devices") and path.startswith("/customers/"):
            return {
                "code": 0,
                "data": {
                    "customer_id": "u1001",
                    "devices": [{"device_id": d} for d in sorted(self.owned_devices)],
                },
            }
        if path.endswith("/tickets") and path.startswith("/customers/"):
            return {
                "code": 0,
                "data": {
                    "customer_id": "u1001",
                    "tickets": [{"ticket_id": t} for t in sorted(self.owned_tickets)],
                },
            }
        for key, value in self.responses.items():
            if key in path:
                return value
        raise RuntimeError(f"请求 GET {path} 返回 HTTP 404：设备不存在")

    async def post_json(self, path: str, json_body: Any = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(path)
        return {"code": 0, "data": {"ticket_id": "TKT-2026-000009", "status_desc": "已转人工"}}


@pytest.fixture()
def env() -> tuple[FlowExecutor, FakeDeviceClient, DialogueState]:
    """构造执行器 + 替身中台 + 空状态。"""
    client = FakeDeviceClient()
    executor = FlowExecutor(ToolRegistry(client))
    state = DialogueState(sender_id="u1001")
    return executor, client, state


def test_warranty_missing_id_then_fill(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """第一轮追问设备编号（零 HTTP）；第二轮填号并只调一次 warranty。"""
    executor, client, state = env
    client.responses["DEV-2026-0001"] = {
        "code": 0,
        "data": {"device_id": "DEV-2026-0001", "warranty_status": "in_warranty", "warranty_deadline": "2027-02-15"},
    }

    first = asyncio.run(executor.handle(state, "帮我查保修"))
    text = " ".join(m.text for m in first.messages)
    assert "设备编号" in text
    assert client.calls == []
    assert state.task is not None and state.task.flow_id == "check_warranty"
    assert state.task.step_id == "ask_device_id"

    second = asyncio.run(executor.handle(state, "DEV-2026-0001"))
    text2 = " ".join(m.text for m in second.messages)
    assert "DEV-2026-0001" in text2
    assert "保修" in text2
    assert "/devices/DEV-2026-0001/warranty" in client.calls
    assert client.calls.count("/devices/DEV-2026-0001/warranty") == 1
    assert state.task is None


def test_warranty_one_shot(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """一句话带设备编号：直接查保修，不追问。"""
    executor, client, state = env
    client.responses["DEV-2026-0001"] = {
        "code": 0,
        "data": {"device_id": "DEV-2026-0001", "warranty_status": "in_warranty", "warranty_deadline": "2027-02-15"},
    }
    result = asyncio.run(executor.handle(state, "DEV-2026-0001 还在保修吗？"))
    text = " ".join(m.text for m in result.messages)
    assert "DEV-2026-0001" in text
    assert "/devices/DEV-2026-0001/warranty" in client.calls
    assert client.calls.count("/devices/DEV-2026-0001/warranty") == 1
    assert state.task is None


def test_warranty_bad_pattern_reask(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """设备编号格式不对：重新追问，不调工具。"""
    executor, client, state = env
    asyncio.run(executor.handle(state, "查保修"))
    result = asyncio.run(executor.handle(state, "编号是 abc"))
    text = " ".join(m.text for m in result.messages)
    assert "设备编号" in text or "DEV-" in text
    assert client.calls == []
    assert state.task is not None


def test_new_intent_while_collecting(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """收槽途中说转人工：不把「转人工」当成槽值，进入转人工确认。"""
    executor, client, state = env
    asyncio.run(executor.handle(state, "帮我查保修"))
    result = asyncio.run(executor.handle(state, "转人工"))
    text = " ".join(m.text for m in result.messages)
    assert "人工" in text or "确认" in text
    if state.task is not None:
        assert state.task.slots.get("device_id") in (None, "")
    # 转人工是 confirm 步，不应直接写穿
    assert state.task is None or state.task.flow_id == "transfer_to_human"


def test_cancel_active_task(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """收槽途中取消：清空任务，不调工具。"""
    executor, client, state = env
    asyncio.run(executor.handle(state, "帮我查保修"))
    result = asyncio.run(executor.handle(state, "取消"))
    assert state.task is None
    assert client.calls == []
    text = " ".join(m.text for m in result.messages)
    assert "取消" in text


def test_tool_error_no_fake_success(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """中台失败：明确失败话术，不写假保修结果，且任务必须结束（禁止卡在 call_tool）。"""
    executor, client, state = env
    client.raise_5xx = True
    result = asyncio.run(executor.handle(state, "DEV-2026-0001 查保修"))
    text = " ".join(m.text for m in result.messages)
    assert "失败" in text or "稍后" in text or "未找到" in text or "没有成功" in text
    assert "在保修期内" not in text
    assert state.task is None


def test_tool_error_does_not_swallow_next_message(
    env: tuple[FlowExecutor, FakeDeviceClient, DialogueState],
) -> None:
    """工具失败后下一句不得重试同一工具，应放行到能力兜底/新意图。"""
    executor, client, state = env
    # 0003 不属于 u1001：归属校验失败，对齐线上截图话术
    asyncio.run(executor.handle(state, "DEV-2026-0003 查保修"))
    assert state.task is None
    assert any(c.startswith("/customers/") for c in client.calls)
    client.calls.clear()

    # 闲聊：不应再碰归属/保修接口
    result = asyncio.run(executor.handle(state, "你好"))
    text = " ".join(m.text for m in result.messages)
    assert "没有成功" not in text
    assert client.calls == []

    # 新意图：可以正常进转人工确认
    result2 = asyncio.run(executor.handle(state, "转人工"))
    text2 = " ".join(m.text for m in result2.messages)
    assert "人工" in text2 or "确认" in text2
    assert not any("warranty" in c for c in client.calls)


def test_ownership_rejects_other_users_device(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """u1001 只拥有 0001/0004：查 0003 不得回保修事实。"""
    executor, client, state = env
    client.responses["DEV-2026-0003"] = {
        "code": 0,
        "data": {"device_id": "DEV-2026-0003", "warranty_status": "expired", "warranty_deadline": "2026-01-15"},
    }
    result = asyncio.run(executor.handle(state, "DEV-2026-0003 是否在保修"))
    text = " ".join(m.text for m in result.messages)
    assert "不属于" in text or "无权" in text or "无法" in text
    assert "有效期" not in text
    assert "/devices/DEV-2026-0003/warranty" not in client.calls
    assert state.task is None


def test_cancel_colloquial_bu_cha_le(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """「不查了」应视作取消，而不是当槽值继续追问。"""
    executor, client, state = env
    asyncio.run(executor.handle(state, "帮我查保修"))
    result = asyncio.run(executor.handle(state, "不查了"))
    text = " ".join(m.text for m in result.messages)
    assert "取消" in text
    assert state.task is None
    assert client.calls == []


def test_confirm_yes_colloquial(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """转人工确认时「是的」应通过。"""
    executor, client, state = env
    asyncio.run(executor.handle(state, "转人工"))
    result = asyncio.run(executor.handle(state, "是的"))
    text = " ".join(m.text for m in result.messages)
    assert "已为您转接" in text or "转接人工" in text
    assert any(p.endswith("/transfers") for p in client.calls)


def test_confirm_chitchat_clarifies_not_auto_yes(env: tuple[FlowExecutor, FakeDeviceClient, DialogueState]) -> None:
    """确认态下说闲聊：应澄清确认/取消，不能当成确认，也不应无限重复同一句。"""
    executor, client, state = env
    asyncio.run(executor.handle(state, "转人工"))
    result = asyncio.run(executor.handle(state, "今天天气怎么样"))
    text = " ".join(m.text for m in result.messages)
    assert "确认" in text and "取消" in text
    assert "已为您转接" not in text
    assert not any(p.endswith("/transfers") for p in client.calls)
