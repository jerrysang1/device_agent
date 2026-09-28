"""API 请求/响应模型：与前端 App.vue 字段对齐。

约定：
    1. ChatRequest 对应前端 POST /api/chat 的 body。
    2. 消息出参字段 role/type/text/object/suggestions 与前端 appendMessage 一致。
    3. 统一包一层 {code, message, data} 与中台风格一致时，可在此扩展。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求。

    Attributes:
        sender_id: 用户ID，如 u1001。
        text: 用户文本；与 object 二选一。
        object: 用户点选的设备/工单卡片，可为空。
    """

    sender_id: str = Field(..., min_length=1, description="用户ID")
    text: Optional[str] = Field(default=None, description="用户文本")
    object: Optional[dict[str, Any]] = Field(default=None, description="业务对象卡片")


class MessageObjectSchema(BaseModel):
    """业务对象卡片出参。

    Attributes:
        type: device 或 ticket。
        id: 对象主键。
        title: 卡片标题。
    """

    type: str = "device"
    id: str = ""
    title: str = ""


class BotMessageSchema(BaseModel):
    """机器人消息出参。

    Attributes:
        role: 固定 bot / user / divider。
        type: text / object / divider。
        text: 文本。
        object: 对象卡片，可空。
        suggestions: 建议词，可空。
    """

    role: str = "bot"
    type: str = "text"
    text: str = ""
    object: Optional[dict[str, Any]] = None
    suggestions: Optional[list[str]] = None


class ChatResponse(BaseModel):
    """聊天响应。

    Attributes:
        messages: 本轮消息列表，前端直接渲染。
        task_status: 当前任务状态，可空。
    """

    messages: list[dict[str, Any]] = Field(default_factory=list)
    task_status: Optional[str] = None


class HistoryResponse(BaseModel):
    """历史消息响应。

    Attributes:
        sender_id: 用户ID。
        messages: 历史消息列表。
    """

    sender_id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)


class HealthData(BaseModel):
    """健康检查数据。"""

    status: str = "ok"
    service: str = "agent-gateway"


class ApiResponse(BaseModel):
    """统一响应包装。

    Attributes:
        code: 0 表示成功。
        message: 提示语。
        data: 业务数据。
    """

    code: int = 0
    message: str = "ok"
    data: Any = None
