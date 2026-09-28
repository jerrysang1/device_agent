"""对话上下文领域模型：业务任务快照与系统流程上下文。

对话引擎里有两条独立的状态轨道：

1. 业务任务（TaskContext）：用户发起的「我要报修」「查保修」，
   对应一条 YAML 流程，会逐步推进 step 并收集 slots。
2. 系统流程（SystemContext）：引擎主动发起的追问或状态反馈，
   优先级高于业务任务——系统刚问完「请提供设备编号」，必须先听回答，
   不能让中途插入的新意图把这次追问吞掉。

设计要点：
    1. 只放数据结构和序列化，不写业务逻辑。
    2. from_dict 一律 data.get(key, default)，旧 JSON 缺字段也不炸。
    3. SystemContext 子类用「注册表 + from_dict」做类型分发，
       从 MySQL 加载时按 type 字段还原成正确的具体类型。
    4. 序列化按 dataclass 字段自动完成：子类只声明字段与 type_name，
       不必为每个子类手写 to_dict / from_dict。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Optional


# ---------------------------------------------------------------------------
# 0. 通用序列化工具（所有 Context 共用）
# ---------------------------------------------------------------------------
def _dump_dataclass(obj: Any) -> dict[str, Any]:
    """把 dataclass 实例序列化成 dict（含子类字段）。

    字段名即 dict 键名；dict / list 做浅拷贝，避免外部引用被改。
    ClassVar（如 type_name）不出现在 fields() 里，不会被序列化。

    Args:
        obj: 任意带 dataclass 字段的实例。

    Returns:
        dict: {字段名: 字段值}。
    """
    result: dict[str, Any] = {}
    for f in fields(obj):
        value = getattr(obj, f.name)
        # 可变类型拷贝一份，防止调用方后续修改影响已序列化数据
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, list):
            value = list(value)
        result[f.name] = value
    return result


def _build_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """按字段声明从 dict 构造 dataclass 实例（缺省字段用类默认值）。

    只取本类声明过的字段，多余键忽略，保证前向兼容。

    Args:
        cls: 目标 dataclass 类型。
        data: 数据字典。

    Returns:
        Any: cls 的实例。
    """
    data = data or {}
    valid_names = {f.name for f in fields(cls)}
    kwargs: dict[str, Any] = {}
    for name in valid_names:
        if name not in data:
            continue  # 缺字段 → 走类默认值
        value = data[name]
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, list):
            value = list(value)
        kwargs[name] = value
    return cls(**kwargs)


@dataclass(slots=True)
class TaskContext:
    """业务任务执行快照：正在跑哪个流程、到哪一步、收集了什么槽位。

    Attributes:
        flow_id: 流程标识，对应 flow_config 里的 flow key。
        step_id: 当前步骤 id，None 表示尚未开始。
        slots: 已收集槽位，如 device_id / problem_type / problem_desc。
    """

    flow_id: str = ""
    step_id: Optional[str] = None
    slots: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为可入库的 dict。

        Returns:
            dict: {flow_id, step_id, slots}。
        """
        return _dump_dataclass(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskContext":
        """从 dict 或数据库 payload 还原任务快照。

        Args:
            data: 任务上下文字典。

        Returns:
            TaskContext: 还原后的任务。
        """
        return _build_dataclass(cls, data)


@dataclass(slots=True)
class SystemContext:
    """系统流程基类：引擎主动发起的回应或追问。

    子类只需：
        1. 声明自己的字段（含默认 flow_id）。
        2. 设置 type_name，用于序列化与类型分发。
    to_dict / from_dict 由基类按字段自动完成。

    Attributes:
        flow_id: 系统流程 id，子类有默认值。
        step_id: 当前步骤 id。
        type_name: 子类类型标识，写入 dict 供分发使用。
    """

    flow_id: str = ""       # 系统流程 id，子类有默认值
    step_id: Optional[str] = None       # 当前步骤 id，None 表示尚未开始
    type_name: ClassVar[str] = "base"

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict，含 type 供 from_dict 分发。

        步骤：
            1. 先写 type（来自 type_name）。
            2. 再并入本实例全部字段（子类字段自动带上）。

        Returns:
            dict: {type, ...字段}。
        """
        result: dict[str, Any] = {"type": self.type_name}
        result.update(_dump_dataclass(self))
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SystemContext":
        """统一反序列化入口，按 type 字段做类型分发。

        步骤：
            1. 仅当以基类身份调用时才分发，避免子类递归。
            2. 命中注册表则构造对应子类。
            3. 未命中则构造基类；字段自动还原，缺省走默认值。

        Args:
            data: 系统上下文字典，建议含 type 字段。

        Returns:
            SystemContext 或其子类实例。
        """
        # 1. 基类调用才做分发
        if cls is SystemContext:
            subcls = _SYSTEM_CONTEXT_TYPES.get(data.get("type", ""), None)
            if subcls is not None:
                return subcls.from_dict(data)
        # 2/3. 字段自动还原
        return _build_dataclass(cls, data)


@dataclass(slots=True)
class CollectSystemContext(SystemContext):
    """收集槽位信息：当前 step 在等用户填某个字段。

    Attributes:
        slot_name: 正在收集的槽位名，如 device_id(未来扩展渲染的时候用到，点击卡片的时候，槽位的名字能够做判断是否需要展示)。
        response: 追问话术或选项草稿。
    """

    flow_id: str = "system_collect_information"
    slot_name: str = ""
    response: dict[str, Any] = field(default_factory=dict)  #{"text": "请输入设备 id"}
    type_name: ClassVar[str] = "collect"


@dataclass(slots=True)
class StartedSystemContext(SystemContext):
    """用户开了一个全新任务。

    Attributes:
        started_flow_id: 新开流程的 id。
        started_flow_name: 新开流程的展示名。
    """

    flow_id: str = "system_task_started"
    started_flow_id: str = ""
    started_flow_name: str = ""
    type_name: ClassVar[str] = "started"


@dataclass(slots=True)
class ResumedSystemContext(SystemContext):
    """从 paused_tasks 恢复此前被中断的任务。

    Attributes:
        resumed_flow_id: 被恢复流程的 id(中断的业务流程 id)。
        resumed_flow_name: 被恢复流程的展示名(中断的业务流程展示名)。
    """

    flow_id: str = "system_task_resumed"
    resumed_flow_id: str = ""
    resumed_flow_name: str = ""
    type_name: ClassVar[str] = "resumed"


@dataclass(slots=True)
class InterruptedSystemContext(SystemContext):
    """当前任务被新任务打断：原任务进 paused_tasks，先跑新任务。

    Attributes:
        interrupted_flow_id: 被打断流程的 id。
        interrupted_flow_name: 被打断流程的展示名。
        started_flow_id: 新开流程的 id。
        started_flow_name: 新开流程的展示名。
    """

    flow_id: str = "system_task_interrupted"
    interrupted_flow_id: str = ""
    interrupted_flow_name: str = ""
    started_flow_id: str = ""
    started_flow_name: str = ""
    type_name: ClassVar[str] = "interrupted"


@dataclass(slots=True)
class CanceledSystemContext(SystemContext):
    """用户主动取消当前任务。

    Attributes:
        canceled_flow_id: 被取消流程的 id。
        canceled_flow_name: 被取消流程的展示名。
    """

    flow_id: str = "system_task_canceled"
    canceled_flow_id: str = ""
    canceled_flow_name: str = ""
    type_name: ClassVar[str] = "canceled"


@dataclass(slots=True)
class CannotHandleSystemContext(SystemContext):
    """引擎无法处理本轮输入：连续工具失败、越权或意图未识别。

    Attributes:
        reason: 失败原因说明，可为空。
    """

    flow_id: str = "system_cannot_handle"
    reason: Optional[str] = None
    type_name: ClassVar[str] = "cannot_handle"


@dataclass(slots=True)
class CompletedSystemContext(SystemContext):
    """任务正常结束。

    Attributes:
        previous_flow_name: 刚完成的流程展示名。
    """

    flow_id: str = "system_completed"
    previous_flow_name: str = ""
    type_name: ClassVar[str] = "completed"


# 类型分发表：type 字符串 → 具体子类
_SYSTEM_CONTEXT_TYPES: dict[str, type] = {
    "collect": CollectSystemContext,
    "started": StartedSystemContext,
    "resumed": ResumedSystemContext,
    "interrupted": InterruptedSystemContext,
    "canceled": CanceledSystemContext,
    "cannot_handle": CannotHandleSystemContext,
    "completed": CompletedSystemContext,
}

# 对外白名单：系统流程 YAML 的 type 必须落在此集合（task 定义模型校验用）
SYSTEM_CONTEXT_TYPE_NAMES: frozenset[str] = frozenset(_SYSTEM_CONTEXT_TYPES)


def create_system_context(data: dict[str, Any]) -> SystemContext:
    """按 type 字段创建系统上下文，对外推荐入口。

    Args:
        data: 系统上下文字典，需含 type 字段。

    Returns:
        SystemContext: 注册表命中的子类实例；未知 type 时返回基类实例。
    """
    return SystemContext.from_dict(data)


if __name__ == "__main__":
    """测：TaskContext 往返 + 7 个 SystemContext 子类类型分发 + 脏数据兜底。"""

    # 1. TaskContext 往返
    task = TaskContext(
        flow_id="create_service_ticket",
        step_id="ask_problem",
        slots={"device_id": "DEV-2026-0001"},
    )
    back = TaskContext.from_dict(task.to_dict())
    assert back.to_dict() == task.to_dict(), "TaskContext 往返失败"
    print("[1] TaskContext:", task.to_dict())

    # 2. 逐个子类：to_dict → 基类入口 from_dict，类型与内容都正确
    samples = [
        CollectSystemContext(slot_name="device_id", response={"ask": "设备编号是？"}),
        StartedSystemContext(started_flow_id="create_service_ticket", started_flow_name="报修建单"),
        ResumedSystemContext(resumed_flow_id="create_service_ticket", resumed_flow_name="报修建单"),
        InterruptedSystemContext(
            interrupted_flow_id="create_service_ticket",
            interrupted_flow_name="报修建单",
            started_flow_id="check_warranty",
            started_flow_name="查保修",
        ),
        CanceledSystemContext(canceled_flow_id="create_service_ticket", canceled_flow_name="报修建单"),
        CannotHandleSystemContext(reason="连续两次工具失败"),
        CompletedSystemContext(previous_flow_name="查保修"),
    ]
    for obj in samples:
        data = obj.to_dict()
        restored = create_system_context(data)
        assert type(restored) is type(obj), f"类型分发失败: {data['type']}"
        assert restored.to_dict() == data, f"往返失败: {data['type']}"
        print(f"[2] {type(restored).__name__}: type={data['type']} ✓")

    # 3. 未知 type 兜底成基类，不抛异常
    unknown = create_system_context({"type": "whatever", "flow_id": "x"})
    assert isinstance(unknown, SystemContext) and type(unknown) is SystemContext
    print("[3] 未知 type 兜底:", type(unknown).__name__)

    # 4. 缺字段也能构造（走类默认值）
    sparse = create_system_context({"type": "collect", "slot_name": "device_id"})
    assert sparse.slot_name == "device_id" and sparse.flow_id == "system_collect_information"
    print("[4] 缺字段构造 ✓")

    print("\ncontexts 模型自测通过 ✓")
