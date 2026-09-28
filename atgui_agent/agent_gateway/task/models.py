"""YAML 流程定义模型：把 flow_config 下的流程描述解析成可执行对象。

职责边界：
    1. 本模块只负责「定义侧」——YAML → 类型化对象，加载时做结构校验。
    2. 运行时状态（跑到哪一步、收了什么槽）在 domain/contexts.py 的 TaskContext。
    3. 执行逻辑在 task/flow/executor.py，只读这里的对象，不碰原始 dict。

设计要点：
    1. 槽位定义与流程步骤都是 dataclass；步骤按 type 注册表分发到子类，
       和 SystemContext 的类型分发同一套路，执行器只 switch 具体类型。
    2. 加载即校验：entry / next 必须能落到真实 step，未知 type 直接抛错，
       避免跑到一半才 KeyError。
    3. 只放数据结构和解析，不写业务推进逻辑——改文案改 YAML，不改本文件。

与 domain/contexts.py 的字段对齐：
    1. AskSlotStep.slot_name ← YAML 键 slot（from_dict 别名），直接喂
       CollectSystemContext.slot_name。
    2. Flow.name → StartedSystemContext.started_flow_name 等展示名字段。
    3. 系统流程 context_type 必须落在 SYSTEM_CONTEXT_TYPE_NAMES 白名单。
    4. write_confirm 工具：need_confirm 默认 True，params.confirmed 必须 True。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Optional

import yaml

from agent_gateway.domain.contexts import SYSTEM_CONTEXT_TYPE_NAMES
from agent_gateway.task.tools import KNOWN_TOOL_ACTIONS

# flow_config 目录：agent_gateway/task/models.py → 上跳两级到仓库根
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
FLOW_CONFIG_DIR = _PROJECT_ROOT / "flow_config"
USER_FLOWS_PATH = FLOW_CONFIG_DIR / "user_flows.yml"
SYSTEM_FLOWS_PATH = FLOW_CONFIG_DIR / "system_flows.yml"

# next 字段的流程终点哨兵值（不是某个 step id）
FLOW_END = "end"


# ---------------------------------------------------------------------------
# 0. 通用解析工具
# ---------------------------------------------------------------------------
def _pick(data: dict[str, Any], cls: type) -> dict[str, Any]:
    """从 dict 取出目标类声明过的字段，多余键忽略。

    Args:
        data: 原始字典（YAML 解析结果）。
        cls: 目标 dataclass 类型。

    Returns:
        dict: 可直接 cls(**kwargs) 的字段子集。
    """
    data = data or {}
    valid = {f.name for f in fields(cls)}
    return {k: data[k] for k in valid if k in data}


def _dump_dataclass(obj: Any) -> dict[str, Any]:
    """把 dataclass 实例序列化成 dict（含子类字段）。

    dict / list 做浅拷贝，避免外部引用被改；ClassVar 不会被序列化。

    Args:
        obj: 任意带 dataclass 字段的实例。

    Returns:
        dict: {字段名: 字段值}。
    """
    result: dict[str, Any] = {}
    for f in fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, list):
            value = list(value)
        result[f.name] = value
    return result


# ---------------------------------------------------------------------------
# 1. 槽位定义（YAML 顶部 slots:）
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FlowSlot:
    """全局槽位定义：名字 → 类型 / 约束 / 说明。

    流程里的 slots: [device_id] 只记名字，真正的约束看这里。

    Attributes:
        name: 槽位名，如 device_id。
        type: 取值类型，string / enum。
        pattern: 正则约束，无约束为 None。
        values: enum 可选值；非 enum 为空列表。
        desc: 给人看的语义说明。
    """

    name: str = ""
    type: str = "string"
    pattern: Optional[str] = None
    values: list[str] = field(default_factory=list)
    desc: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict。

        Returns:
            dict: {name, type, pattern?, values?, desc}。
        """
        return _dump_dataclass(self)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "FlowSlot":
        """从 YAML 段落构造槽位。

        Args:
            name: 槽位名（来自 map 的 key）。
            data: 该槽位的定义字典。

        Returns:
            FlowSlot: 槽位对象。
        """
        data = data or {}
        values = data.get("values") or []
        return cls(
            name=name,
            type=str(data.get("type") or "string"),
            pattern=data.get("pattern"),
            values=[str(v) for v in values],
            desc=str(data.get("desc") or ""),
        )


# ---------------------------------------------------------------------------
# 2. 流程步骤（steps 列表元素，按 type 分发）
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FlowStep:
    """流程步骤基类：只保留各步共有的 id / next。

    子类声明自己的字段并设置 type_name；from_dict 在基类入口按 type 分发。

    Attributes:
        id: 步骤唯一 id，TaskContext.step_id 记录的就是它。
        next: 下一步 id；FLOW_END 表示流程结束。
        type_name: 步骤类型标识，对应 YAML 的 type 字段。
    """

    id: str = ""
    next: str = FLOW_END
    type_name: ClassVar[str] = "base"

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict，含 type 供还原分发。

        Returns:
            dict: {type, ...字段}。
        """
        result: dict[str, Any] = {"type": self.type_name}
        result.update(_dump_dataclass(self))
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlowStep":
        """统一反序列化入口，按 type 字段分发到具体步骤子类。

        步骤：
            1. 仅当以基类身份调用时才分发，避免子类递归。
            2. 命中注册表则构造对应子类。
            3. 未命中抛 ValueError——定义文件写错必须在加载期暴露。

        Args:
            data: 步骤字典，需含 type。

        Returns:
            FlowStep: 对应子类实例。

        Raises:
            ValueError: type 未注册。
        """
        # 1. 基类调用才分发
        if cls is FlowStep:
            step_type = str(data.get("type") or "")
            subcls = _STEP_TYPES.get(step_type)
            if subcls is None:
                raise ValueError(f"未知步骤 type: {step_type!r}，已知: {sorted(_STEP_TYPES)}")
            return subcls.from_dict(data)
        # 2/3. 字段自动还原
        return cls(**_pick(data, cls))


@dataclass(slots=True)
class AskSlotStep(FlowStep):
    """收集槽位：向用户追问一个字段，填完进 next。

    字段名与 CollectSystemContext.slot_name 对齐；YAML 键名是 slot，
    from_dict 做别名映射，执行器可以直接 slot_name=step.slot_name。

    Attributes:
        slot_name: 要收集的槽位名；系统流程步骤可为空（运行时注入）。
        ask: 追问话术，支持 ${...} 模板。
        options: 候选项 [{value, label}]，或模板串 "${slot_options}"。
    """

    slot_name: str = ""
    ask: str = ""
    options: Optional[list[dict[str, str]] | str] = None
    type_name: ClassVar[str] = "ask_slot"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AskSlotStep":
        """从 step 字典构造；兼容 YAML 键 slot → 字段 slot_name。

        Args:
            data: 步骤字典。

        Returns:
            AskSlotStep: 实例。
        """
        data = dict(data or {})
        if "slot_name" not in data and "slot" in data:
            data["slot_name"] = data["slot"]
        return cls(**_pick(data, cls))


@dataclass(slots=True)
class CallToolStep(FlowStep):
    """调用中台工具：读接口直接调，写接口必须先确认。

    Attributes:
        action: 工具名，与中台 GET /tools 注册表一致。
        permission: read 或 write_confirm。
        params: 入参模板，值里可写 ${slots.xxx} / ${tool.xxx}。
        need_confirm: 调用前是否要过确认闸门。write_confirm 默认 True
            （YAML 约定写操作必须确认），显式写出则以 YAML 为准。
    """

    action: str = ""
    permission: str = "read"
    params: dict[str, Any] = field(default_factory=dict)
    need_confirm: bool = False
    type_name: ClassVar[str] = "call_tool"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CallToolStep":
        """从 step 字典构造；write_confirm 缺 need_confirm 时默认 True。

        Args:
            data: 步骤字典。

        Returns:
            CallToolStep: 实例。
        """
        data = dict(data or {})
        obj = cls(**_pick(data, cls))
        # 1. YAML 未写 need_confirm 时，按 permission 补默认
        if "need_confirm" not in data and obj.permission == "write_confirm":
            obj.need_confirm = True
        return obj


@dataclass(slots=True)
class ConfirmStep(FlowStep):
    """写操作前确认：用户说确认才进 next，否则走取消。

    Attributes:
        ask: 确认话术。
        need_confirm: 恒为 True——type=confirm 本身就是闸门，
            from_dict 会强制写回 True，防止 YAML 误写 false。
    """

    ask: str = ""
    need_confirm: bool = True
    type_name: ClassVar[str] = "confirm"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfirmStep":
        """从 step 字典构造；need_confirm 强制 True。

        Args:
            data: 步骤字典。

        Returns:
            ConfirmStep: 实例。
        """
        obj = cls(**_pick(data or {}, cls))
        obj.need_confirm = True
        return obj


@dataclass(slots=True)
class ReplyStep(FlowStep):
    """固定/模板回复：把结果说给用户，一般接在 call_tool 之后。

    Attributes:
        say: 回复模板，支持 ${slots.xxx} / ${tool.xxx}。
        suggestions: 建议词列表，可为空。
    """

    say: str = ""
    suggestions: list[str] = field(default_factory=list)
    type_name: ClassVar[str] = "reply"


# type 字符串 → 具体步骤子类
_STEP_TYPES: dict[str, type] = {
    "ask_slot": AskSlotStep,
    "call_tool": CallToolStep,
    "confirm": ConfirmStep,
    "reply": ReplyStep,
}


def parse_step(data: dict[str, Any]) -> FlowStep:
    """把一个 step 字典解析成具体步骤对象。

    Args:
        data: steps 列表中的元素。

    Returns:
        FlowStep: 具体子类实例。

    Raises:
        ValueError: type 未知或缺 id。
    """
    step_id = str(data.get("id") or "")
    if not step_id:
        raise ValueError("步骤缺少 id")
    step = FlowStep.from_dict(data)
    return step


# ---------------------------------------------------------------------------
# 3. 流程（flows: / system_flows: 的一项）
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Flow:
    """一条完整流程：入口 + 槽位名列表 + 有序步骤。

    Attributes:
        flow_id: 流程 id，TaskContext.flow_id 引用它。
        name: 展示名，用于回复文案。
        desc: 流程说明。
        entry: 入口步骤 id。
        slots: 本流程用到的槽位名列表（约束查全局 FlowSlot）。
        steps: 步骤列表，顺序与 YAML 一致。
        kind: user 业务流程 / system 系统流程。
        context_type: 系统流程对应的 SystemContext type；业务流程为空。
    """

    flow_id: str = ""
    name: str = ""
    desc: str = ""
    entry: str = ""
    slots: list[str] = field(default_factory=list)
    steps: list[FlowStep] = field(default_factory=list)
    kind: str = "user"
    context_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（steps 也转成 dict，键名对齐 YAML）。

        系统流程把 context_type 写回 YAML 的 type 键，保证 to_dict 往返。

        Returns:
            dict: 流程定义字典。
        """
        result = _dump_dataclass(self)
        result["steps"] = [s.to_dict() for s in self.steps]
        # 1. 系统流程用 YAML 键名 type，去掉模型侧 context_type
        if self.kind == "system":
            result["type"] = result.pop("context_type", "")
        return result

    @classmethod
    def from_dict(cls, flow_id: str, data: dict[str, Any], *, kind: str = "user") -> "Flow":
        """从 YAML 流程段落构造 Flow。

        步骤：
            1. 取公共字段。
            2. 逐步 parse_step，组装 steps。
            3. 系统流程带上 context_type（YAML 的 type 字段）。

        Args:
            flow_id: 流程 id（来自 map 的 key）。
            data: 该流程的定义字典。
            kind: user 或 system。

        Returns:
            Flow: 流程对象。
        """
        # 1. 公共字段
        steps_raw = data.get("steps") or []
        slot_names = data.get("slots") or []
        # 2. 逐步解析
        steps = [parse_step(s) for s in steps_raw]
        # 3. 系统流程的 type 对应 SystemContext
        context_type = ""
        if kind == "system":
            context_type = str(data.get("type") or "")
        return cls(
            flow_id=flow_id,
            name=str(data.get("name") or ""),
            desc=str(data.get("desc") or ""),
            entry=str(data.get("entry") or ""),
            slots=[str(s) for s in slot_names],
            steps=steps,
            kind=kind,
            context_type=context_type,
        )

    def step_map(self) -> dict[str, FlowStep]:
        """按 id 索引步骤，方便执行器 O(1) 取下一步。

        Returns:
            dict: {step_id: FlowStep}。
        """
        return {s.id: s for s in self.steps}

    def get_step(self, step_id: str) -> Optional[FlowStep]:
        """按 id 取步骤。

        Args:
            step_id: 步骤 id。

        Returns:
            FlowStep | None: 命中返回步骤，否则 None。
        """
        for s in self.steps:
            if s.id == step_id:
                return s
        return None


# ---------------------------------------------------------------------------
# 4. 流程目录（整份 YAML 解析结果）
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FlowCatalog:
    """全部流程定义的目录：全局槽位 + 业务流程 + 系统流程。

    Attributes:
        slots: 全局槽位，key 为槽位名。
        flows: 业务流程，key 为 flow_id。
        system_flows: 系统流程，key 为 flow_id。
    """

    slots: dict[str, FlowSlot] = field(default_factory=dict)
    flows: dict[str, Flow] = field(default_factory=dict)
    system_flows: dict[str, Flow] = field(default_factory=dict)

    def get_flow(self, flow_id: str) -> Optional[Flow]:
        """按 id 查流程，业务优先，再查系统。

        Args:
            flow_id: 流程 id。

        Returns:
            Flow | None: 命中的流程。
        """
        if flow_id in self.flows:
            return self.flows[flow_id]
        return self.system_flows.get(flow_id)

    def get_slot(self, name: str) -> Optional[FlowSlot]:
        """按名查全局槽位定义。

        Args:
            name: 槽位名。

        Returns:
            FlowSlot | None: 命中的槽位。
        """
        return self.slots.get(name)


# ---------------------------------------------------------------------------
# 5. 解析 / 校验 / 加载
# ---------------------------------------------------------------------------
def parse_slots(data: dict[str, Any]) -> dict[str, FlowSlot]:
    """解析顶部 slots 段。

    Args:
        data: {槽位名: 定义} 字典。

    Returns:
        dict: {槽位名: FlowSlot}。
    """
    result: dict[str, FlowSlot] = {}
    for name, body in (data or {}).items():
        result[str(name)] = FlowSlot.from_dict(str(name), body)
    return result


def parse_flows(data: dict[str, Any], *, kind: str = "user") -> dict[str, Flow]:
    """解析 flows / system_flows 段。

    Args:
        data: {flow_id: 定义} 字典。
        kind: user 或 system。

    Returns:
        dict: {flow_id: Flow}。
    """
    result: dict[str, Flow] = {}
    for flow_id, body in (data or {}).items():
        result[str(flow_id)] = Flow.from_dict(str(flow_id), body, kind=kind)
    return result


def validate_flow(flow: Flow, slots: dict[str, FlowSlot], *, kind: str = "user") -> None:
    """校验单条流程的结构完整性。

    步骤：
        1. 步骤 id 不得重复。
        2. entry 必须是真实 step。
        3. 每个 next 必须是 FLOW_END 或真实 step。
        4. 必须存在能走到 FLOW_END 的路径（防止死循环/断头路）。
        5. 从 entry 出发必须能到达全部步骤（防止不可达孤儿节点）。
        6. 业务流程：ask_slot 槽位、call_tool 工具名合法；write_confirm 必须有 confirm 前置。

    注意：
        params.confirmed: true 只是 YAML 配置字段，表示「流程设计上假定已确认」，
        **不能**当作真实用户授权。最终写入必须由中台服务端签发绑定
        会话/资源/参数摘要/有效期的确认凭证后才能执行。

    Args:
        flow: 流程对象。
        slots: 全局槽位表。
        kind: user 或 system（业务流程才查槽位/工具/写闸门）。

    Raises:
        ValueError: 结构不完整。
    """
    # 1. 步骤 id 唯一
    id_list = [s.id for s in flow.steps]
    if len(id_list) != len(set(id_list)):
        dup = sorted({i for i in id_list if id_list.count(i) > 1})
        raise ValueError(f"流程 {flow.flow_id} 步骤 id 重复: {dup}")

    ids = set(id_list)
    by_id = {s.id: s for s in flow.steps}

    # 2. entry
    if not flow.entry:
        raise ValueError(f"流程 {flow.flow_id} 缺少 entry")
    if flow.entry not in ids:
        raise ValueError(f"流程 {flow.flow_id} 的 entry={flow.entry!r} 不在 steps 中: {sorted(ids)}")

    # 3. next 目标存在
    for step in flow.steps:
        if step.next != FLOW_END and step.next not in ids:
            raise ValueError(
                f"流程 {flow.flow_id} 步骤 {step.id} 的 next={step.next!r} 不是 {FLOW_END} 也不在 steps 中"
            )

    # 4. 从 entry 沿 next 走，必须能到 end（线性 next 的可达性）
    reachable: set[str] = set()
    confirm_seen: set[str] = set()  # 沿途遇到过 ConfirmStep 的位置
    cursor: Optional[str] = flow.entry
    reached_end = False
    for _ in range(len(flow.steps) + 1):
        if cursor is None or cursor == FLOW_END:
            reached_end = cursor == FLOW_END
            break
        if cursor in reachable:
            raise ValueError(f"流程 {flow.flow_id} 在步骤 {cursor} 出现 next 环，无法到达 {FLOW_END}")
        reachable.add(cursor)
        step = by_id[cursor]
        if isinstance(step, ConfirmStep):
            confirm_seen.add(cursor)
        cursor = step.next
    if not reached_end:
        raise ValueError(f"流程 {flow.flow_id} 从 entry 无法到达 {FLOW_END}（断头路或死循环）")

    # 5. 不可达孤儿步骤
    orphans = ids - reachable
    if orphans:
        raise ValueError(f"流程 {flow.flow_id} 存在不可达步骤: {sorted(orphans)}")

    # 6. 业务流程：槽位 / 工具 / 写闸门
    if kind == "user":
        for step in flow.steps:
            if isinstance(step, AskSlotStep) and step.slot_name and step.slot_name not in slots:
                raise ValueError(
                    f"流程 {flow.flow_id} 步骤 {step.id} 引用了未定义槽位 {step.slot_name!r}，"
                    f"已知: {sorted(slots)}"
                )
            if isinstance(step, CallToolStep):
                if step.action not in KNOWN_TOOL_ACTIONS:
                    raise ValueError(
                        f"流程 {flow.flow_id} 步骤 {step.id} 使用未知工具 {step.action!r}，"
                        f"已知: {sorted(KNOWN_TOOL_ACTIONS)}"
                    )
                if step.permission == "write_confirm":
                    # 配置层闸门：必须有 confirm 前置，且 params.confirmed 仅为过渡字段
                    if not any(isinstance(by_id[s], ConfirmStep) for s in _steps_before(flow, step.id)):
                        raise ValueError(
                            f"流程 {flow.flow_id} 步骤 {step.id} 是 write_confirm，"
                            f"但路径上没有前置 confirm 步骤"
                        )
                    if step.params.get("confirmed") is not True:
                        raise ValueError(
                            f"流程 {flow.flow_id} 步骤 {step.id} 是 write_confirm，"
                            f"params.confirmed 必须为 True（仅配置字段，非真实授权），"
                            f"实际: {step.params.get('confirmed')!r}"
                        )
                if step.params is not None and not isinstance(step.params, dict):
                    raise ValueError(f"流程 {flow.flow_id} 步骤 {step.id} 的 params 必须是 mapping")

    # 7. 系统流程 type 必须能在 SystemContext 注册表还原
    if kind == "system" and flow.context_type and flow.context_type not in SYSTEM_CONTEXT_TYPE_NAMES:
        raise ValueError(
            f"系统流程 {flow.flow_id} 的 type={flow.context_type!r} 不在 SystemContext 白名单: "
            f"{sorted(SYSTEM_CONTEXT_TYPE_NAMES)}"
        )


def _steps_before(flow: Flow, step_id: str) -> list[str]:
    """返回从 entry 到 step_id（不含）路径上的步骤 id 列表（线性 next）。"""
    path: list[str] = []
    cursor: Optional[str] = flow.entry
    seen: set[str] = set()
    while cursor and cursor != FLOW_END and cursor not in seen:
        if cursor == step_id:
            return path
        seen.add(cursor)
        path.append(cursor)
        step = flow.get_step(cursor)
        cursor = step.next if step else None
    return path


def load_catalog(
    user_path: Path | str = USER_FLOWS_PATH,
    system_path: Path | str = SYSTEM_FLOWS_PATH,
) -> FlowCatalog:
    """加载业务 + 系统两份 YAML，解析并校验成 FlowCatalog。

    步骤：
        1. yaml.safe_load 读两份文件。
        2. 解析 slots / flows / system_flows。
        3. 逐条 validate_flow，失败抛 ValueError。

    Args:
        user_path: user_flows.yml 路径。
        system_path: system_flows.yml 路径。

    Returns:
        FlowCatalog: 校验通过的完整目录。

    Raises:
        ValueError: YAML 结构或引用不合法。
    """
    # 1. 读文件
    user_raw = _read_yaml(user_path)
    system_raw = _read_yaml(system_path)
    # 2. 解析
    slots = parse_slots(user_raw.get("slots") or {})
    flows = parse_flows(user_raw.get("flows") or {}, kind="user")
    system_flows = parse_flows(system_raw.get("system_flows") or {}, kind="system")
    # 3. 校验
    for flow in flows.values():
        validate_flow(flow, slots, kind="user")
    for flow in system_flows.values():
        validate_flow(flow, slots, kind="system")
        if not flow.context_type:
            raise ValueError(f"系统流程 {flow.flow_id} 缺少 type（对接 SystemContext）")
    return FlowCatalog(slots=slots, flows=flows, system_flows=system_flows)


def _read_yaml(path: Path | str) -> dict[str, Any]:
    """读取并解析 YAML 文件。

    Args:
        path: YAML 文件路径。

    Returns:
        dict: 根节点字典。

    Raises:
        ValueError: 文件不存在或不是 mapping。
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"流程 YAML 不存在: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"流程 YAML 根节点必须是 mapping: {p}")
    return data


if __name__ == "__main__":
    """手动冒烟：只验证真实 YAML 能加载。

    正式断言与失败用例见 agent_gateway/test/test_flow_models.py。
    本入口**不能**替代 pytest，也不代表业务闭环已跑通。
    """
    catalog = load_catalog()
    print("user flows:", sorted(catalog.flows))
    print("system flows:", sorted(catalog.system_flows))
    print("slots:", sorted(catalog.slots))
    print("请跑: python -m pytest atgui_agent/agent_gateway/test/test_flow_models.py -q")
