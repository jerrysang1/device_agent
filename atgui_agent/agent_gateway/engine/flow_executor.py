"""YAML 流程执行器：按 FlowCatalog 推进 TaskContext，不写 HTTP 细节。

职责边界：
    1. 读定义（task.models）→ 更新运行时状态（domain.state）→ 组装 ProcessResult。
    2. 工具调用走 task.tools.ToolRegistry，不在本文件拼 URL。
    3. 一轮最多推进 MAX_STEPS 步，防止定义写错导致死循环。

设计要点：
    1. 有任务先续任务；无任务按意图开新流程。
    2. ask_slot 收槽时先识别「取消 / 新意图」，避免把「转人工」当成槽值。
    3. 模板只替换 ${slots.xxx} / ${tool.xxx}，不做 eval。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from agent_gateway.domain.contexts import TaskContext
from agent_gateway.domain.messages import ProcessResult
from agent_gateway.domain.state import DialogueState
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
)
from agent_gateway.task.tools import ToolRegistry, ToolResult

MAX_STEPS = 30

DEVICE_ID_PATTERN = re.compile(r"DEV-\d{4}-\d{4}")
TICKET_ID_PATTERN = re.compile(r"TKT-\d{4}-\d{6}")
_TEMPLATE_PATTERN = re.compile(r"\$\{(slots|tool)\.([A-Za-z0-9_]+)\}")

# 意图关键词 → 流程 id（确定性路由，M2 再换成 LLM 规划）
_INTENT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("转人工", "人工客服", "人工"), "transfer_to_human"),
    (("保修", "质保", "warranty"), "check_warranty"),
    (("报修", "建单", "维修单", "工单"), "create_service_ticket"),
    (("进度", "修到哪", "物流"), "get_repair_progress"),
]

# 确认：短语用整句精确匹配，避免「是」误伤「是否/但是」
_CONFIRM_EXACT = {
    "是", "是的", "是的呀", "是啊", "嗯", "嗯嗯", "嗯呢",
    "好", "好的", "好呀", "好啊", "好嘞", "行", "行的", "对", "对的",
    "确认", "确定", "可以", "可以的", "没问题", "ok", "okay", "yes", "y",
}
_CONFIRM_PHRASES = ("确认", "确定", "没问题", "可以的")

# 取消：覆盖「不查了/不转了」等放弃当前任务的口语
_CANCEL_EXACT = {
    "取消", "算了", "算了吧", "不要了", "不要", "不用了", "不用",
    "不查了", "不查", "不想查", "不查啦",
    "不转了", "不转", "不想转", "不用转", "不转人工", "不要转",
    "no", "nope", "否",
}
_CANCEL_PHRASES = ("取消", "算了", "不查了", "不用了", "不转了", "不想查", "不想转", "不要了")


class FlowExecutor:
    """把「用户文本 + DialogueState」推进成机器人回复，并就地改状态。"""

    def __init__(self, tools: ToolRegistry, catalog: Optional[FlowCatalog] = None) -> None:
        """注入工具表与流程目录。

        Args:
            tools: 工具注册表。
            catalog: 流程目录；缺省从 flow_config 加载。
        """
        self.tools = tools
        self.catalog = catalog if catalog is not None else load_catalog()
        self._tool_data: dict[str, Any] = {}
        self._current_sender: str = ""

    async def handle(self, state: DialogueState, user_text: str) -> ProcessResult:
        """处理一轮输入，返回回复并更新 state.task。

        步骤：
            1. 归一文本；空文本给能力提示。
            2. 显式取消 / 确认分支。
            3. 有任务先续任务（收槽或推进）；无任务按意图开流程。
            4. 无法识别则回空消息，交给上层闲聊/知识兜底。

        Args:
            state: 对话状态（就地修改 task / slots）。
            user_text: 用户本条文本。

        Returns:
            ProcessResult: 机器人消息；无流程可处理时 messages 可能为空。
        """
        result = ProcessResult()
        self._tool_data = {}
        # 为什么：工具归属校验要用会话身份，不能信 body 里单独传的 customer_id
        self._current_sender = state.sender_id or ""
        raw = (user_text or "").strip()

        # 1. 空输入给能力说明，不进流程
        if not raw:
            result.append_text(_capability_tip())
            return result

        # 2. 全局取消优先——口语「不查了」必须先于「当槽值」被识别
        if _is_cancel(raw):
            if state.task is not None:
                name = self._flow_name(state.task.flow_id)
                state.cancel_task()
                result.append_text(f"已取消「{name}」。还有其他可以帮您的吗？")
            else:
                result.append_text("当前没有进行中的任务。")
            return result

        # 3. 有任务先续跑（收槽 / 确认 / 异常 step 续推）
        if state.task is not None:
            handled = await self._continue_task(state, raw, result)
            if handled:
                return result

        # 4. 无任务（或续跑让出）：按意图开新流程
        flow_id = _detect_flow_id(raw)
        if flow_id is None:
            return result

        flow = self.catalog.get_flow(flow_id)
        if flow is None or flow.kind != "user":
            return result

        # 5. 插话：原任务压栈，避免新意图吞掉未完成任务
        if state.task is not None:
            old_name = self._flow_name(state.task.flow_id)
            state.interrupt_task()
            result.append_text(f"先处理您的新问题，稍后我们回到「{old_name}」。")

        # 6. 建任务；一句话里带编号则预填槽，支持单轮走完
        task = TaskContext(flow_id=flow_id, step_id=flow.entry, slots={})
        _extract_known_slots(flow, task, raw)
        state.start_task(task)
        await self._advance(state=state, flow=flow, task=task, result=result)
        return result

    # ------------------------------------------------------------------
    # 任务续跑
    # ------------------------------------------------------------------
    async def _continue_task(self, state: DialogueState, raw: str, result: ProcessResult) -> bool:
        """续跑当前任务。True=已消费本条输入；False=应走新开流程。"""
        task = state.task
        if task is None:
            return False
        flow = self.catalog.get_flow(task.flow_id)
        if flow is None:
            state.end_task()
            result.append_text("当前任务定义已失效，已为您结束。请重新发起。")
            return True

        step = flow.get_step(task.step_id) if task.step_id else flow.get_step(flow.entry)

        if isinstance(step, ConfirmStep):
            return await self._handle_confirm(state, flow, task, step, raw, result)

        if isinstance(step, AskSlotStep):
            new_flow = _detect_flow_id(raw)
            if new_flow and new_flow != task.flow_id:
                return False  # 插话，交给 handle 开新流程
            return await self._fill_slot(state, flow, task, step, raw, result)

        # step 停在 call_tool/reply（异常）——继续推进
        await self._advance(state=state, flow=flow, task=task, result=result)
        return True

    async def _handle_confirm(
        self,
        state: DialogueState,
        flow: Flow,
        task: TaskContext,
        step: ConfirmStep,
        raw: str,
        result: ProcessResult,
    ) -> bool:
        """确认步：确认/取消/新意图/闲聊澄清。

        规则：
            1. 肯定答复（是的/好的/确认…）→ 进 next。
            2. 取消词在 handle 已全局处理；这里再兜一层短否定。
            3. 识别到其他业务意图 → 交回 handle 插话（压栈）。
            4. 否则澄清：请明确确认或取消，不把闲聊当确认。
        """
        # 1. 肯定答复才推进——写操作禁止「默认同意」
        if _is_confirm(raw):
            task.step_id = step.next
            await self._advance(state=state, flow=flow, task=task, result=result)
            return True
        # 2. 否定则取消当前任务
        if _is_cancel(raw):
            name = self._flow_name(task.flow_id)
            state.cancel_task()
            result.append_text(f"已取消「{name}」。还有其他可以帮您的吗？")
            return True
        # 3. 其它业务意图 → 让 handle 插话，不把「查保修」当确认
        if _detect_flow_id(raw) is not None:
            return False
        # 4. 闲聊/没听懂 → 澄清；重复问但附带可点选项，避免死循环式复读
        ask = _render(step.ask, task.slots, self._tool_data)
        result.append_text(
            f"{ask}\n请回复「确认」继续，或「取消」放弃。",
            suggestions=["确认", "取消"],
        )
        result.task_status = "WAITING_CONFIRMATION"
        return True

    async def _fill_slot(
        self,
        state: DialogueState,
        flow: Flow,
        task: TaskContext,
        step: AskSlotStep,
        raw: str,
        result: ProcessResult,
    ) -> bool:
        """把用户文本填进当前槽位，然后继续推进。"""
        value = _parse_slot_value(step, raw, self.catalog.get_slot(step.slot_name))
        if value is None:
            result.append_text(
                _render(step.ask, task.slots, self._tool_data),
                suggestions=_option_labels(step),
            )
            result.task_status = "COLLECTING_SLOTS"
            return True
        task.slots[step.slot_name] = value
        task.step_id = step.next
        await self._advance(state=state, flow=flow, task=task, result=result)
        return True

    # ------------------------------------------------------------------
    # 推进
    # ------------------------------------------------------------------
    async def _advance(
        self,
        *,
        state: DialogueState,
        flow: Flow,
        task: TaskContext,
        result: ProcessResult,
    ) -> None:
        """从当前 step_id 往前推，直到要用户输入或流程结束。"""
        steps = flow.step_map()
        if not task.step_id:
            task.step_id = flow.entry

        for _ in range(MAX_STEPS):
            if not task.step_id or task.step_id == FLOW_END:
                self._finish_task(state, task, result)
                return

            step = steps.get(task.step_id)
            if step is None:
                state.end_task()
                result.append_text("流程步骤丢失，已为您结束当前任务。")
                return

            if isinstance(step, AskSlotStep):
                if task.slots.get(step.slot_name):
                    task.step_id = step.next
                    continue
                result.append_text(
                    _render(step.ask, task.slots, self._tool_data),
                    suggestions=_option_labels(step),
                )
                result.task_status = "COLLECTING_SLOTS"
                return

            if isinstance(step, ConfirmStep):
                result.append_text(_render(step.ask, task.slots, self._tool_data))
                result.task_status = "WAITING_CONFIRMATION"
                return

            if isinstance(step, CallToolStep):
                done = await self._run_tool(step, task, result)
                if not done:
                    # 为什么：失败若停在 call_tool，下一轮会无限重试同一工具并吞掉闲聊/新意图
                    state.end_task()
                    return
                task.step_id = step.next
                continue

            if isinstance(step, ReplyStep):
                result.append_text(
                    _render(step.say, task.slots, self._tool_data),
                    suggestions=list(step.suggestions or []),
                )
                task.step_id = step.next
                continue

            task.step_id = step.next

        state.end_task()
        result.append_text("本轮流程步骤过多，已暂停。请重新发起。")

    async def _run_tool(self, step: CallToolStep, task: TaskContext, result: ProcessResult) -> bool:
        """执行工具并写入 ${tool.xxx}。False=已回复错误、停止推进。"""
        params = _render_params(step.params, task.slots, self._tool_data)
        # 为什么：归属校验依据是会话里的 sender_id，禁止 YAML/前端另传 customer_id 绕过
        if "customer_id" not in params and self._current_sender:
            params["customer_id"] = self._current_sender
        tool_result: ToolResult = await self.tools.call(step, params)
        if not tool_result.ok:
            result.append_text(
                f"很抱歉，{step.action} 没有成功：{tool_result.error}。请稍后重试或转人工。",
                suggestions=["转人工"],
            )
            result.error = tool_result.error
            return False
        self._tool_data.update(tool_result.data)
        return True

    def _finish_task(self, state: DialogueState, task: TaskContext, result: ProcessResult) -> None:
        """流程走到 end：清任务并给收尾提示。"""
        flow_name = self._flow_name(task.flow_id) if task.flow_id else ""
        state.end_task()
        result.task_status = "COMPLETED"
        if not result.messages and flow_name:
            result.append_text(f"「{flow_name}」已处理完毕。还有其他可以帮您的吗？")

    def _flow_name(self, flow_id: str) -> str:
        flow = self.catalog.get_flow(flow_id) if flow_id else None
        return flow.name if flow else (flow_id or "任务")


# ---------------------------------------------------------------------------
# 纯函数辅助
# ---------------------------------------------------------------------------
def _capability_tip() -> str:
    return (
        "我可以帮您：查保修（提供设备编号如 DEV-2026-0001）、"
        "报修建工单、查维修进度、转人工、查询设备手册。"
    )


def _match_words(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(w in text or w in lowered for w in words)


def _is_confirm(text: str) -> bool:
    """口语肯定：整句精确匹配优先，避免「是否/但是」误判。"""
    t = (text or "").strip().lower()
    if t in _CONFIRM_EXACT:
        return True
    return any(p in text for p in _CONFIRM_PHRASES)


def _is_cancel(text: str) -> bool:
    """口语否定/放弃：不查了、不转了、算了…"""
    t = (text or "").strip().lower()
    if t in _CANCEL_EXACT:
        return True
    return any(p in text for p in _CANCEL_PHRASES)


def _detect_flow_id(text: str) -> Optional[str]:
    """按关键词选流程：转人工 > 保修 > 报修 > 进度。"""
    for keywords, flow_id in _INTENT_RULES:
        if _match_words(text, keywords):
            return flow_id
    return None


def _extract_known_slots(flow: Flow, task: TaskContext, raw: str) -> None:
    """从整句预提取槽值，支持一句话走完流程。"""
    upper = raw.upper()
    device = DEVICE_ID_PATTERN.search(upper)
    if device and "device_id" in flow.slots:
        task.slots["device_id"] = device.group(0)
    ticket = TICKET_ID_PATTERN.search(upper)
    if ticket and "ticket_id" in flow.slots:
        task.slots["ticket_id"] = ticket.group(0)


def _parse_slot_value(step: AskSlotStep, raw: str, slot_def: Optional[FlowSlot]) -> Optional[str]:
    """把用户文本解析成槽值；不合法返回 None（继续追问）。"""
    name = step.slot_name
    text = raw.strip()

    if name == "device_id":
        match = DEVICE_ID_PATTERN.search(text.upper())
        return match.group(0) if match else None

    if name == "ticket_id":
        match = TICKET_ID_PATTERN.search(text.upper())
        return match.group(0) if match else None

    if name == "problem_type" or (slot_def and slot_def.type == "enum" and slot_def.values):
        options = step.options if isinstance(step.options, list) else []
        lowered = text.lower()
        for opt in options:
            if not isinstance(opt, dict):
                continue
            if str(opt.get("value", "")).lower() == lowered or str(opt.get("label", "")) == text:
                return str(opt.get("value"))
        for value in (slot_def.values if slot_def else []):
            if str(value).lower() == lowered:
                return str(value)
        return None

    return text if text else None


def _option_labels(step: AskSlotStep) -> list[str]:
    if not isinstance(step.options, list):
        return []
    return [str(opt["label"]) for opt in step.options if isinstance(opt, dict) and opt.get("label")]


def _render(template: str, slots: dict[str, Any], tool: dict[str, Any]) -> str:
    """替换 ${slots.x} / ${tool.x}；缺失显示 —，绝不 eval。"""

    def repl(match: re.Match[str]) -> str:
        ns, key = match.group(1), match.group(2)
        source = slots if ns == "slots" else tool
        value = source.get(key)
        return "—" if value is None or value == "" else str(value)

    return _TEMPLATE_PATTERN.sub(repl, template or "")


def _render_params(params: dict[str, Any], slots: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    """渲染参数模板；字符串值做替换，其它类型原样。"""
    rendered: dict[str, Any] = {}
    for key, value in (params or {}).items():
        rendered[key] = _render(value, slots, tool) if isinstance(value, str) else value
    return rendered


_CATALOG: Optional[FlowCatalog] = None


def get_flow_executor(tools: ToolRegistry) -> FlowExecutor:
    """获取绑定 tools 的执行器（流程目录进程内共享）。"""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_catalog()
    return FlowExecutor(tools, catalog=_CATALOG)
