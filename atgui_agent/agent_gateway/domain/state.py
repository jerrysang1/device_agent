"""对话状态聚合根：一个用户一份完整记忆，含会话与轮次生命周期。

职责：
    1. DialogueState：聚合根，承载任务、系统追问、暂停栈、会话与轮次。
    2. Session / Turn：会话边界与「一轮对话」封装。
    3. 生命周期方法：begin_turn / commit_turn、start_session / close_session、超时清场。
    4. to_dict / from_dict：整份状态与 JSON 互转，便于一行入库、原样还原。

设计要点：
    1. 一个用户 = 一行状态；变更都落在内存对象上，持久化在 service 层。
    2. current_context（系统追问）优先级高于 task（业务任务）。
    3. pending_turn 是内存暂存：begin_turn 先写暂存，commit_turn 才进 session.turns，
       引擎中途失败不会把半截轮次写进历史。
    4. Session 用时间戳判断超时；超时后 reset_running_state_for_new_session 清场。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from agent_gateway.domain.contexts import SystemContext, TaskContext
from agent_gateway.domain.messages import Message, MessageObject

# 会话超时：无活动超过该秒数视为过期（默认 60 分钟）
SESSION_TIMEOUT_SECONDS = 60 * 60


@dataclass(slots=True)
class Turn:
    """一轮对话：用户输入 + 机器人回复列表。

    Attributes:
        turn_id: 轮次唯一标识。
        user_message: 本条用户消息；机器人主动发起时可为 None。
        bot_messages: 本条机器人回复列表。
    """

    turn_id: str = ""
    user_message: Optional[Message] = None
    bot_messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict。

        Returns:
            dict: {turn_id, user_message?, bot_messages}。
        """
        return {
            "turn_id": self.turn_id,
            "user_message": self.user_message.to_dict() if self.user_message else None,
            "bot_messages": [m.to_dict() for m in self.bot_messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Turn":
        """从 dict 还原一轮对话。

        Args:
            data: 轮次字典。

        Returns:
            Turn: 还原后的轮次。
        """
        data = data or {}
        user = data.get("user_message")
        bots = data.get("bot_messages") or []
        return cls(
            turn_id=str(data.get("turn_id") or ""),
            user_message=Message.from_dict(user) if user else None,
            bot_messages=[Message.from_dict(m) for m in bots],
        )


@dataclass(slots=True)
class Session:
    """会话：一次「打开工作台到闲置超时」的边界，内含多轮 Turn。

    Attributes:
        session_id: 会话ID。
        started_at: 开始时间戳（秒）。
        last_activity_at: 最后活动时间戳，用于超时判断。
        closed_at: 关闭时间戳；None 表示仍在进行。
        turns: 本会话内的轮次列表。
    """

    session_id: str = ""
    started_at: float = 0.0
    last_activity_at: float = 0.0
    closed_at: Optional[float] = None
    turns: list[Turn] = field(default_factory=list)

    def touch(self) -> None:
        """刷新最后活动时间（每次用户输入时调用）。"""
        self.last_activity_at = time.time()

    def is_expired(self, now: Optional[float] = None, timeout: float = SESSION_TIMEOUT_SECONDS) -> bool:
        """判断会话是否超时。

        Args:
            now: 当前时间戳，缺省取 time.time()。
            timeout: 超时秒数。

        Returns:
            bool: 超时且未关闭则 True。
        """
        if self.closed_at is not None:
            return False
        current = now if now is not None else time.time()
        return (current - self.last_activity_at) > timeout

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict。

        Returns:
            dict: 会话字段与轮次列表。
        """
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_activity_at": self.last_activity_at,
            "closed_at": self.closed_at,
            "turns": [t.to_dict() for t in self.turns],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """从 dict 还原会话。

        Args:
            data: 会话字典。

        Returns:
            Session: 还原后的会话。
        """
        data = data or {}
        turns = data.get("turns") or []
        return cls(
            session_id=str(data.get("session_id") or ""),
            started_at=float(data.get("started_at") or 0.0),
            last_activity_at=float(data.get("last_activity_at") or 0.0),
            closed_at=data.get("closed_at"),
            turns=[Turn.from_dict(t) for t in turns],
        )


@dataclass(slots=True)
class DialogueState:
    """对话状态聚合根：一个用户一份，整体序列化入库。

    Attributes:
        sender_id: 用户ID。
        current_context: 系统追问上下文，优先处理。
        task: 当前业务任务快照。
        paused_tasks: 被插话打断、等待恢复的任务栈。
        focused_object: 前端聚焦对象，可为空。
        sessions: 历史会话列表。
        current_session_id: 当前会话ID，None 表示无活动会话。
        pending_turn: 本轮暂存；commit 后进入 session.turns 并清空。
    """

    sender_id: str = ""
    current_context: Optional[SystemContext] = None
    task: Optional[TaskContext] = None
    paused_tasks: list[TaskContext] = field(default_factory=list)
    focused_object: Optional[MessageObject] = None
    sessions: list[Session] = field(default_factory=list)
    current_session_id: Optional[str] = None
    pending_turn: Optional[Turn] = None

    # ---- 会话生命周期 ----
    def current_session(self) -> Optional[Session]:
        """按 current_session_id 查找当前会话。

        Returns:
            Session | None: 当前会话；不存在则 None。
        """
        if not self.current_session_id:
            return None
        for session in self.sessions:
            if session.session_id == self.current_session_id:
                return session
        return None

    def start_session(self) -> Session:
        """开启会话；已有活动会话则复用并刷新活动时间。

        Returns:
            Session: 当前活动会话。
        """
        session = self.current_session()
        if session is not None and session.closed_at is None:
            session.touch()
            return session
        now = time.time()
        session = Session(
            session_id=str(uuid.uuid4()),
            started_at=now,
            last_activity_at=now,
        )
        self.sessions.append(session)
        self.current_session_id = session.session_id
        return session

    def close_session(self) -> None:
        """关闭当前会话（写 closed_at，清空 current_session_id）。"""
        session = self.current_session()
        if session is not None:
            session.closed_at = time.time()
        self.current_session_id = None

    def reset_running_state_for_new_session(self) -> None:
        """会话超时或强制新开时清场：丢弃运行中状态，保留历史 sessions/turns。

        步骤：
            1. 清空业务任务、系统追问、暂停栈、聚焦对象。
            2. 丢弃未提交的 pending_turn（半截轮次不进历史）。
            3. 断开当前会话引用。
        """
        self.task = None
        self.current_context = None
        self.paused_tasks = []
        self.focused_object = None
        self.pending_turn = None
        self.current_session_id = None

    def touch_session(self) -> None:
        """刷新会话活动时间；会话已失效则自动重置并新开。"""
        session = self.current_session()
        if session is None or session.is_expired():
            if session is not None:
                self.reset_running_state_for_new_session()
            self.start_session()
        else:
            session.touch()

    # ---- Turn 生命周期（两阶段提交）----
    def begin_turn(self, user_message: Optional[Message] = None) -> Turn:
        """开始一轮对话：写入 pending_turn 暂存区。

        Args:
            user_message: 本轮用户消息；机器人主动通知可为 None。

        Returns:
            Turn: 刚创建的暂存轮次。

        Raises:
            RuntimeError: 当前无活动会话（请先 start_session）。
        """
        session = self.current_session()
        if session is None:
            raise RuntimeError("当前无活动会话，请先调用 start_session()")
        turn = Turn(turn_id=str(uuid.uuid4()), user_message=user_message, bot_messages=[])
        self.pending_turn = turn
        return turn

    def commit_turn(self) -> Optional[Turn]:
        """提交暂存轮次：写入当前会话历史，并清空 pending_turn。

        Returns:
            Turn | None: 提交的轮次；无 pending 则 None。
        """
        session = self.current_session()
        if session is None or self.pending_turn is None:
            return None
        turn = self.pending_turn
        session.turns.append(turn)
        session.touch()
        self.pending_turn = None
        return turn

    def append_bot_to_pending(self, message: Message) -> None:
        """向暂存轮次追加机器人回复（commit 前调用）。

        Args:
            message: 机器人消息。
        """
        if self.pending_turn is not None:
            self.pending_turn.bot_messages.append(message)

    # ---- 任务生命周期 ----
    def start_task(self, task: TaskContext) -> None:
        """开启业务任务。

        Args:
            task: 新的业务任务快照。
        """
        self.task = task

    def end_task(self) -> None:
        """结束当前业务任务。"""
        self.task = None

    def cancel_task(self) -> None:
        """取消任务：同时清空业务任务与系统追问。"""
        self.task = None
        self.current_context = None

    def start_system_context(self, context: SystemContext) -> None:
        """开启/覆盖系统追问上下文。

        Args:
            context: 系统流程上下文。
        """
        self.current_context = context

    def end_system_context(self) -> None:
        """结束系统追问。"""
        self.current_context = None

    def interrupt_task(self) -> None:
        """中断当前业务任务：压入暂停栈。"""
        if self.task is not None:
            self.paused_tasks.append(self.task)
            self.task = None

    def resume_task(self, flow_id: Optional[str] = None) -> Optional[TaskContext]:
        """恢复暂停的任务。

        Args:
            flow_id: 指定流程 id；None 则恢复栈顶。

        Returns:
            TaskContext | None: 恢复的任务。
        """
        if not flow_id:
            return self.pop_paused_task()
        for index, task in enumerate(self.paused_tasks):
            if task.flow_id == flow_id:
                self.task = self.paused_tasks.pop(index)
                return self.task
        return self.pop_paused_task()

    def set_slots(self, slots: dict[str, Any]) -> None:
        """合并槽位到当前任务。

        Args:
            slots: 槽位键值。

        Raises:
            RuntimeError: 无活动任务。
        """
        if self.task is None:
            raise RuntimeError("当前没有活动任务，无法写入槽位")
        self.task.slots.update(slots)

    def remove_slot(self, slot_name: str) -> None:
        """删除当前任务的某个槽位。

        Args:
            slot_name: 槽位名。
        """
        if self.task is not None:
            self.task.slots.pop(slot_name, None)

    @property
    def current_active_context(self) -> Optional[object]:
        """优先上下文：系统追问 > 业务任务。

        Returns:
            SystemContext | TaskContext | None。
        """
        return self.current_context or self.task

    def push_paused_task(self) -> None:
        """interrupt_task 的别名，保留兼容。"""
        self.interrupt_task()

    def pop_paused_task(self) -> Optional[TaskContext]:
        """弹出最近暂停的任务并设为当前任务。

        Returns:
            TaskContext | None: 恢复的任务；栈空则 None。
        """
        if not self.paused_tasks:
            return None
        self.task = self.paused_tasks.pop()
        return self.task

    def append_turn(self, user_message: Optional[Message], bot_messages: list[Message]) -> Turn:
        """直接追加一轮对话到「当前会话」；无会话则先开一个。

        适合简单场景；需要两阶段时用 begin_turn / commit_turn。

        Args:
            user_message: 用户消息。
            bot_messages: 机器人回复列表。

        Returns:
            Turn: 刚追加的轮次。
        """
        session = self.start_session()
        turn = Turn(
            turn_id=str(uuid.uuid4()),
            user_message=user_message,
            bot_messages=list(bot_messages),
        )
        session.turns.append(turn)
        session.touch()
        return turn

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        """把整份状态序列化成可入库的 dict。

        Returns:
            dict: 一行 JSON 即可完整还原本状态（含 sessions 与 pending_turn）。
        """
        result: dict[str, Any] = {"sender_id": self.sender_id}
        if self.current_context is not None:
            result["current_context"] = self.current_context.to_dict()
        if self.task is not None:
            result["task"] = self.task.to_dict()
        if self.focused_object is not None:
            result["focused_object"] = self.focused_object.to_dict()
        result["paused_tasks"] = [t.to_dict() for t in self.paused_tasks]
        result["sessions"] = [s.to_dict() for s in self.sessions]
        result["current_session_id"] = self.current_session_id
        result["pending_turn"] = self.pending_turn.to_dict() if self.pending_turn else None
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DialogueState":
        """从 dict / 数据库 JSON 还原聚合根。

        Args:
            data: 聚合根字典。

        Returns:
            DialogueState: 还原后的状态。
        """
        data = data or {}
        ctx = data.get("current_context")
        task = data.get("task")
        paused = data.get("paused_tasks") or []
        focused = data.get("focused_object")
        sessions = data.get("sessions") or []
        pending = data.get("pending_turn")
        # 兼容旧数据：只有 turns 没有 sessions 时，包成一个匿名会话
        if not sessions and data.get("turns"):
            sessions = [{
                "session_id": "legacy",
                "started_at": 0,
                "last_activity_at": 0,
                "turns": data.get("turns") or [],
            }]
        return cls(
            sender_id=str(data.get("sender_id") or ""),
            current_context=SystemContext.from_dict(ctx) if ctx else None,
            task=TaskContext.from_dict(task) if task else None,
            paused_tasks=[TaskContext.from_dict(t) for t in paused],
            focused_object=MessageObject.from_dict(focused) if focused else None,
            sessions=[Session.from_dict(s) for s in sessions],
            current_session_id=data.get("current_session_id"),
            pending_turn=Turn.from_dict(pending) if pending else None,
        )


if __name__ == "__main__":
    """自测：会话/轮次两阶段 + 任务压栈恢复 + 超时清场 + 序列化往返。"""

    from agent_gateway.domain.contexts import CollectSystemContext

    # 1. 开会话 → begin_turn → 追加 bot → commit_turn
    state = DialogueState(sender_id="u1001")
    session = state.start_session()
    turn = state.begin_turn(Message.user_text("DEV-2026-0001 还在保修吗？"))
    state.append_bot_to_pending(Message.bot_text("在保修期内。"))
    committed = state.commit_turn()
    assert committed is not None and committed.turn_id == turn.turn_id
    assert state.pending_turn is None
    assert len(session.turns) == 1
    print("[1] begin/commit_turn ✓")

    # 2. 任务压栈 / 精确恢复
    state.start_task(TaskContext(flow_id="create_service_ticket", step_id="ask"))
    state.start_system_context(CollectSystemContext(slot_name="device_id"))
    state.interrupt_task()
    assert state.task is None and len(state.paused_tasks) == 1
    resumed = state.resume_task("create_service_ticket")
    assert resumed is not None and resumed.flow_id == "create_service_ticket"
    print("[2] interrupt/resume_task ✓")

    # 3. 超时清场
    state.reset_running_state_for_new_session()
    assert state.task is None and state.current_context is None and state.pending_turn is None
    assert state.current_session_id is None
    print("[3] reset_running_state_for_new_session ✓")

    # 4. 整份序列化往返
    state.append_turn(Message.user_text("你好"), [Message.bot_text("您好")])
    data = state.to_dict()
    back = DialogueState.from_dict(data)
    assert back.to_dict() == data, "DialogueState 往返失败"
    assert back.sessions and back.sessions[0].turns
    print("[4] 往返一致 sessions =", len(back.sessions))
    print("state 模型自测通过 ✓")
