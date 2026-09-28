"""状态仓储：DialogueState 与消息历史的持久化。

设计：
    1. 协议方法 load_state / save_state / append_messages / list_messages。
    2. MemoryStateRepository：测试与本地冒烟用。
    3. DbStateRepository：写 chat_messages 表，状态 JSON 写 agent_tasks 辅助行（type=dialogue_state）。
"""

from __future__ import annotations

from typing import Any, Optional

from agent_gateway.infrastructure.database import AgentTask, ChatMessage, get_session


class MemoryStateRepository:
    """内存仓储：不落库，仅供测试替身或临时演示。"""

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


class DbStateRepository:
    """数据库仓储：消息进 chat_messages，聚合根 JSON 进 agent_tasks。"""

    async def load_state(self, sender_id: str) -> Optional[dict[str, Any]]:
        """加载聚合根 JSON。

        步骤：
            1. 按 sender_id + task_type=dialogue_state 查最新一条。
            2. 有则解析 slots 里的 state_json。
        """
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(AgentTask)
                .where(AgentTask.sender_id == sender_id, AgentTask.task_type == "dialogue_state")
                .order_by(AgentTask.id.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return (row.slots or {}).get("state_json")

    async def save_state(self, sender_id: str, data: dict[str, Any]) -> None:
        """保存聚合根 JSON（upsert 语义：有则改，无则插）。"""
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(AgentTask)
                .where(AgentTask.sender_id == sender_id, AgentTask.task_type == "dialogue_state")
                .order_by(AgentTask.id.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is None:
                session.add(
                    AgentTask(
                        sender_id=sender_id,
                        task_type="dialogue_state",
                        status="COMPLETED",
                        slots={"state_json": data},
                    )
                )
            else:
                row.slots = {"state_json": data}

    async def append_messages(self, sender_id: str, messages: list[dict[str, Any]]) -> None:
        """批量追加消息到 chat_messages。"""
        async with get_session() as session:
            for m in messages:
                session.add(
                    ChatMessage(
                        sender_id=sender_id,
                        role=m.get("role", "bot"),
                        message_type=m.get("type", "text"),
                        content=m.get("text", "") or "",
                        payload=m if m.get("object") or m.get("suggestions") else None,
                    )
                )

    async def list_messages(self, sender_id: str) -> list[dict[str, Any]]:
        """按时间读取历史消息。"""
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(ChatMessage).where(ChatMessage.sender_id == sender_id).order_by(ChatMessage.id.asc())
            )
            rows = result.scalars().all()
            out = []
            for r in rows:
                item: dict[str, Any] = {"role": r.role, "type": r.message_type, "text": r.content}
                if r.payload:
                    item.update({k: v for k, v in r.payload.items() if k in ("object", "suggestions")})
                out.append(item)
            return out


def get_state_repository():
    """默认返回数据库仓储。"""
    return DbStateRepository()
