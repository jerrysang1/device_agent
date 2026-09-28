"""流程定义模型正式测试：真实 YAML 加载 + 结构校验失败用例。

覆盖 models.py 原 __main__ 冒烟断言，并补充重复 id / 未知工具 / 未知槽位 /
不可达 / 死循环 / 缺 end / 写操作无 confirm 前置等失败路径。

说明：
    params.confirmed: true 只是流程配置字段，不是真实用户授权；
    真实写入仍依赖中台服务端确认凭证（P1，本文件不测）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_gateway.domain.contexts import SYSTEM_CONTEXT_TYPE_NAMES
from agent_gateway.task.models import (
    FLOW_END,
    AskSlotStep,
    CallToolStep,
    ConfirmStep,
    Flow,
    FlowCatalog,
    FlowSlot,
    ReplyStep,
    load_catalog,
    parse_step,
    validate_flow,
)

SLOTS = {
    "device_id": FlowSlot(name="device_id", type="string", pattern=r"DEV-\\d{4}-\\d{4}"),
}


def _flow(steps: list[dict], entry: str = "a", flow_id: str = "f") -> Flow:
    return Flow.from_dict(flow_id, {"name": "x", "entry": entry, "steps": steps}, kind="user")


# ---------------------------------------------------------------------------
# 1. 真实 YAML 冒烟（原 __main__ 核心断言）
# ---------------------------------------------------------------------------
def test_load_real_catalog_user_flows() -> None:
    catalog = load_catalog()
    assert "check_warranty" in catalog.flows
    assert "create_service_ticket" in catalog.flows
    assert "get_repair_progress" in catalog.flows
    assert "transfer_to_human" in catalog.flows
    warranty = catalog.flows["check_warranty"]
    assert warranty.entry == "ask_device_id"
    assert len(warranty.steps) == 3


def test_load_real_catalog_step_dispatch() -> None:
    create = load_catalog().flows["create_service_ticket"]
    by_id = create.step_map()
    assert isinstance(by_id["ask_device_id"], AskSlotStep)
    assert isinstance(by_id["confirm_create"], ConfirmStep)
    assert isinstance(by_id["create_ticket"], CallToolStep)
    assert isinstance(by_id["reply_created"], ReplyStep)
    assert by_id["ask_device_id"].slot_name == "device_id"
    assert by_id["confirm_create"].need_confirm is True
    assert by_id["create_ticket"].need_confirm is True
    assert by_id["create_ticket"].params.get("confirmed") is True


def test_load_real_catalog_system_types() -> None:
    catalog = load_catalog()
    sys_types = {f.context_type for f in catalog.system_flows.values()}
    assert sys_types == set(SYSTEM_CONTEXT_TYPE_NAMES)
    sys_flow = catalog.system_flows["system_collect_information"]
    dumped = sys_flow.to_dict()
    assert dumped.get("type") == "collect"
    assert "context_type" not in dumped
    assert Flow.from_dict(sys_flow.flow_id, dumped, kind="system").context_type == "collect"


def test_ask_slot_roundtrip() -> None:
    step = parse_step({"id": "a", "type": "ask_slot", "slot": "device_id", "ask": "x", "next": FLOW_END})
    dumped = step.to_dict()
    assert dumped["type"] == "ask_slot"
    back = AskSlotStep.from_dict(dumped)
    assert back.slot_name == "device_id"


def test_slot_constraints() -> None:
    catalog = load_catalog()
    device = catalog.get_slot("device_id")
    assert device is not None and device.pattern is not None
    problem = catalog.get_slot("problem_type")
    assert problem is not None and problem.values


# ---------------------------------------------------------------------------
# 2. 失败路径
# ---------------------------------------------------------------------------
def test_rejects_duplicate_step_ids() -> None:
    flow = _flow(
        [
            {"id": "a", "type": "reply", "say": "1", "next": "b"},
            {"id": "b", "type": "reply", "say": "2", "next": "end"},
            {"id": "b", "type": "reply", "say": "3", "next": "end"},
        ]
    )
    with pytest.raises(ValueError, match="重复"):
        validate_flow(flow, SLOTS)


def test_rejects_invalid_entry() -> None:
    flow = _flow([{"id": "a", "type": "reply", "say": "hi", "next": FLOW_END}], entry="nope")
    with pytest.raises(ValueError, match="entry"):
        validate_flow(flow, SLOTS)


def test_rejects_dangling_next() -> None:
    flow = _flow([{"id": "a", "type": "reply", "say": "ok", "next": "missing"}])
    with pytest.raises(ValueError, match="missing"):
        validate_flow(flow, SLOTS)


def test_rejects_unknown_slot() -> None:
    flow = _flow([{"id": "a", "type": "ask_slot", "slot": "ghost", "ask": "?", "next": FLOW_END}])
    with pytest.raises(ValueError, match="ghost"):
        validate_flow(flow, SLOTS)


def test_rejects_unknown_tool() -> None:
    flow = _flow(
        [
            {"id": "a", "type": "call_tool", "action": "drop_database", "permission": "read", "params": {}, "next": FLOW_END}
        ]
    )
    with pytest.raises(ValueError, match="drop_database"):
        validate_flow(flow, SLOTS)


def test_rejects_unreachable_step() -> None:
    flow = _flow(
        [
            {"id": "a", "type": "reply", "say": "1", "next": FLOW_END},
            {"id": "orphan", "type": "reply", "say": "2", "next": FLOW_END},
        ]
    )
    with pytest.raises(ValueError, match="不可达"):
        validate_flow(flow, SLOTS)


def test_rejects_cycle_without_end() -> None:
    flow = _flow(
        [
            {"id": "a", "type": "reply", "say": "1", "next": "b"},
            {"id": "b", "type": "reply", "say": "2", "next": "a"},
        ]
    )
    with pytest.raises(ValueError, match="环|无法到达"):
        validate_flow(flow, SLOTS)


def test_rejects_missing_end() -> None:
    # 断头：next 都合法但没有一步指向 end，且循环被上一规则抓不到时用缺 end
    # 这里用单步 next 指向自己以外的合法 id 形成「永远到不了 end」
    flow = _flow([{"id": "a", "type": "reply", "say": "1", "next": "a"}])
    with pytest.raises(ValueError, match="环|无法到达|end"):
        validate_flow(flow, SLOTS)


def test_rejects_write_without_confirm_predecessor() -> None:
    flow = _flow(
        [
            {
                "id": "write",
                "type": "call_tool",
                "action": "create_service_ticket",
                "permission": "write_confirm",
                "params": {"confirmed": True, "device_id": "${slots.device_id}"},
                "next": FLOW_END,
            }
        ],
        entry="write",
    )
    with pytest.raises(ValueError, match="confirm"):
        validate_flow(flow, SLOTS)


def test_rejects_write_without_params_confirmed() -> None:
    flow = _flow(
        [
            {"id": "c", "type": "confirm", "ask": "ok?", "next": "w"},
            {
                "id": "w",
                "type": "call_tool",
                "action": "create_service_ticket",
                "permission": "write_confirm",
                "params": {"device_id": "x"},
                "next": FLOW_END,
            },
        ],
        entry="c",
    )
    with pytest.raises(ValueError, match="confirmed"):
        validate_flow(flow, SLOTS)


def test_params_confirmed_is_config_only_not_auth() -> None:
    """params.confirmed=true 仅是配置字段，加载器只校验「写了 true」，
    不构成真实用户授权；真实写入须服务端确认凭证（另测 / P1）。"""
    flow = _flow(
        [
            {"id": "c", "type": "confirm", "ask": "ok?", "next": "w"},
            {
                "id": "w",
                "type": "call_tool",
                "action": "transfer_to_human",
                "permission": "write_confirm",
                "params": {"confirmed": True},
                "next": FLOW_END,
            },
        ],
        entry="c",
    )
    # 配置校验可通过
    validate_flow(flow, SLOTS)
    step = flow.get_step("w")
    assert isinstance(step, CallToolStep)
    # 但字段本身不携带任何身份/会话/资源绑定
    assert set(step.params.keys()) == {"confirmed"}


def test_rejects_invalid_params_type() -> None:
    # params 在 from_dict 会尽量保留；validate 要求 mapping
    step = parse_step(
        {
            "id": "w",
            "type": "call_tool",
            "action": "check_warranty",
            "permission": "read",
            "params": ["not", "a", "dict"],
            "next": FLOW_END,
        }
    )
    assert isinstance(step, CallToolStep)
    flow = Flow.from_dict(
        "f",
        {"name": "x", "entry": "w", "steps": [{"id": "w", "type": "call_tool", "action": "check_warranty", "permission": "read", "params": 123, "next": FLOW_END}]},
        kind="user",
    )
    # models.CallToolStep.params 注解是 dict，from_dict 可能把 int 塞进来
    with pytest.raises(ValueError, match="params"):
        validate_flow(flow, SLOTS)


def test_rejects_unknown_step_type() -> None:
    with pytest.raises(ValueError, match="未知步骤"):
        parse_step({"id": "a", "type": "eval_code", "next": FLOW_END})
