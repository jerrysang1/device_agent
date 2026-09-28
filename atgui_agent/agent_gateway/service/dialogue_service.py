"""对话服务：load → process → save 事务边界。

职责：
    1. 读写 DialogueState 与消息历史（仓储抽象，测试可替换）。
    2. 调用引擎处理本轮消息。
    3. 保证每条用户消息与机器人回复可从 history 读回。
"""

from __future__ import annotations

from typing import Any, Optional

from agent_gateway.domain.messages import Message, MessageObject
from agent_gateway.domain.state import DialogueState
from agent_gateway.engine.stub_brain import handle_message


class DialogueService:
    """对话应用服务。"""

    def __init__(self, repository: Any, device_client: Any) -> None:
        """注入仓储与中台客户端。

        Args:
            repository: 状态仓储（load_state/save_state/append_messages/list_messages）。
            device_client: 中台客户端。
        """
        self.repository = repository
        self.device_client = device_client

    async def _load(self, sender_id: str) -> DialogueState:
        """加载或初始化聚合根。"""
        data = await self.repository.load_state(sender_id) if _is_async(self.repository.load_state) else self.repository.load_state(sender_id)
        if data:
            return DialogueState.from_dict(data)
        return DialogueState(sender_id=sender_id)

    async def _save(self, state: DialogueState) -> None:
        """保存聚合根。"""
        payload = state.to_dict()
        if _is_async(self.repository.save_state):
            await self.repository.save_state(state.sender_id, payload)
        else:
            self.repository.save_state(state.sender_id, payload)

    async def chat(
        self,
        sender_id: str,
        text: str,
        user_object: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """处理一轮对话，返回前端 ChatResponse 字段。

        步骤：
            1. 加载 DialogueState（多轮任务进度）。
            2. 组装用户消息（文本或对象卡片）。
            3. 引擎推进（FlowExecutor 就地改 state.task）。
            4. 消息 + 状态落库，返回前端 messages。

        Args:
            sender_id: 用户ID。
            text: 用户文本；可为空（纯卡片消息）。
            user_object: 用户点选的设备/工单卡片，可空。

        Returns:
            dict: {messages: [...], task_status: ...}。
        """
        # 1. 为什么必须先 load：收槽/插话都依赖上次的 task/step_id
        state = await self._load(sender_id)

        # 2. 用户消息入历史（卡片优先作为 OBJECT 类型）
        if user_object:
            user_msg = Message.user_object(MessageObject.from_dict(user_object))
        else:
            user_msg = Message.user_text(text)

        # 3. 业务处理：state 交给引擎，不是只读不用
        result = await handle_message(
            text,
            sender_id,
            self.device_client,
            state=state,
            user_object=user_object,
        )

        # 4. 出参模型：BotMessage → 前端 dict（保留 images）
        bot_msgs: list[Message] = []
        for b in result.messages:
            if b.object is not None:
                bot_msgs.append(Message.bot_object(b.object, b.text))
            else:
                bot_msgs.append(Message.bot_text(b.text, b.suggestions, b.images))
        bot_dicts = [m.to_dict() for m in bot_msgs]

        # 5. 持久化消息 + 状态（P1 应同事务，当前分步写）
        out_messages = [user_msg.to_dict()] + bot_dicts
        await self._append_messages(sender_id, out_messages)
        state.append_turn(user_msg, [Message.from_dict(m) for m in bot_dicts])
        await self._save(state)

        return {
            "messages": bot_dicts,
            "task_status": state.task.flow_id if state.task else None,
        }

    async def history(self, sender_id: str) -> list[dict[str, Any]]:
        """读取历史消息。

        Args:
            sender_id: 用户ID。

        Returns:
            list: 消息字典列表。
        """
        if _is_async(self.repository.list_messages):
            return await self.repository.list_messages(sender_id)
        return self.repository.list_messages(sender_id)

    async def _append_messages(self, sender_id: str, messages: list[dict[str, Any]]) -> None:
        """追加消息（兼容同步/异步仓储）。"""
        if _is_async(self.repository.append_messages):
            await self.repository.append_messages(sender_id, messages)
        else:
            self.repository.append_messages(sender_id, messages)


def _is_async(func: Any) -> bool:
    """判断可调用对象是否为协程函数。"""
    import inspect

    return inspect.iscoroutinefunction(func)
