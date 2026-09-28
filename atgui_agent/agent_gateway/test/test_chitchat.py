"""闲聊轨道测试：问候/客套应有自然回复，且不得抢走业务意图。"""

from __future__ import annotations

import asyncio

from agent_gateway.chitchat.handler import reply as chitchat_reply
from agent_gateway.domain.state import DialogueState
from agent_gateway.engine.flow_executor import FlowExecutor
from agent_gateway.engine.stub_brain import CAPABILITY_TIP, handle_message
from agent_gateway.task.tools import ToolRegistry


class FakeDeviceClient:
    """中台替身：默认不发起真实 HTTP。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_json(self, path: str, **kwargs):
        self.calls.append(path)
        if path.endswith("/devices") and path.startswith("/customers/"):
            return {"code": 0, "data": {"customer_id": "u1001", "devices": []}}
        raise RuntimeError(f"请求 GET {path} 返回 HTTP 404：设备不存在")

    async def post_json(self, path: str, json_body=None, **kwargs):
        self.calls.append(path)
        return {"code": 0, "data": {"ticket_id": "", "status_desc": "已转人工"}}


def test_chitchat_greeting_not_capability_tip() -> None:
    """「你好」应走闲聊自我介绍，而不是能力清单原文。"""
    text = chitchat_reply("你好")
    assert text is not None
    assert "设备售后助手" in text
    assert CAPABILITY_TIP not in text


def test_chitchat_does_not_steal_business_intent() -> None:
    """带业务词的句子不得当闲聊。"""
    assert chitchat_reply("你好，帮我查保修") is None
    assert chitchat_reply("我要报修") is None
    assert chitchat_reply("转人工") is None


def test_stub_brain_hello_returns_chitchat() -> None:
    """端到端：你好 → 闲聊回复；谢谢 → 客套；且不进 warranty。"""
    client = FakeDeviceClient()
    state = DialogueState(sender_id="u1001")
    result = asyncio.run(handle_message("你好", "u1001", client, state=state))
    text = " ".join(m.text for m in result.messages)
    assert "设备售后助手" in text
    assert "没有成功" not in text
    assert client.calls == []

    result2 = asyncio.run(handle_message("谢谢", "u1001", client, state=state))
    text2 = " ".join(m.text for m in result2.messages)
    assert "不客气" in text2 or "应该" in text2
    assert CAPABILITY_TIP not in text2
    assert client.calls == []


def test_stub_brain_business_still_reaches_flow() -> None:
    """业务意图不受闲聊影响，仍进保修收槽。"""
    client = FakeDeviceClient()
    state = DialogueState(sender_id="u1001")
    result = asyncio.run(handle_message("查保修", "u1001", client, state=state))
    text = " ".join(m.text for m in result.messages)
    assert "设备编号" in text or "DEV-" in text
    assert state.task is not None
    assert state.task.flow_id == "check_warranty"
