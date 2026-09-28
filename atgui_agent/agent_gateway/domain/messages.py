"""消息领域模型：业务对象卡片、机器人回复、统一消息条目与引擎出参。

本模块只放数据结构和序列化，不写业务逻辑。字段与前端消息协议
（role / type / text / object / suggestions）一一对应，可直接落库
chat_messages.payload，也可直接作为 ChatResponse 出参。

设计要点：
    1. text / object / suggestions 的序列化只写一遍（_dump_content / _load_content），
       BotMessage 与 Message 共用，避免两处漂移。
    2. 类型用 MessageType 枚举，序列化取 .value，反序列化走 from_value 容错。
    3. 全部 dataclass 开 slots=True：大量消息对象时更省内存、属性访问更快，
       且不能动态挂脏字段——对纯数据 DTO 正合适。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MessageType(Enum):
    """消息类型。

    序列化用 .value 得到 "text" / "object" / "divider"；
    反序列化用 from_value，脏数据不会抛异常。

    Attributes:
        TEXT: 纯文本消息。
        OBJECT: 业务对象卡片（设备 / 工单）。
        DIVIDER: 历史分隔线。
    """

    TEXT = "text"
    OBJECT = "object"
    DIVIDER = "divider"

    @classmethod
    def from_value(cls, value: str, default: Optional["MessageType"] = None) -> "MessageType":
        """按字符串安全还原枚举。

        未命中时返回 default 而不是抛 ValueError，因为历史库里的旧值
        不该让整条对话流炸掉。

        Args:
            value: 字符串类型值，如 "text"。
            default: 兜底枚举，缺省为 TEXT。

        Returns:
            MessageType: 还原后的枚举。
        """
        if default is None:
            default = cls.TEXT
        for item in cls:
            if item.value == value:
                return item
        return default


def _dump_content(
    text: str,
    obj: Optional["MessageObject"],
    suggestions: Optional[list[str]],
    images: Optional[list[str]] = None,
) -> dict[str, Any]:
    """把「文本 + 对象 + 建议词 + 图片」序列化成 dict。

    BotMessage 与 Message 的内容部分完全一致，抽成公共函数只维护一处。

    Args:
        text: 文本内容。
        obj: 业务对象卡片，可为 None。
        suggestions: 建议词列表，可为 None。
        images: 图片 URL 列表（手册截图等），可为 None。

    Returns:
        dict: 形如 {"text": ..., "object"?: ..., "suggestions"?: ..., "images"?: ...}。
        可选字段仅在非空时出现，方便前端直接判空。
    """
    # 1. 始终带 text
    result: dict[str, Any] = {"text": text}
    # 2. 对象卡片：只在有内容时下发
    if obj is not None:
        result["object"] = obj.to_dict()
    # 3. 建议词：非空才下发
    if suggestions:
        result["suggestions"] = list(suggestions)
    # 4. 图片：非空才下发，前端渲染成缩略图而非长 URL
    if images:
        result["images"] = list(images)
    return result


def _load_content(
    data: dict[str, Any],
) -> tuple[str, Optional["MessageObject"], Optional[list[str]], Optional[list[str]]]:
    """把 dict 还原成「文本 + 对象 + 建议词 + 图片」。

    与 _dump_content 配对，供 BotMessage.from_dict / Message.from_dict 复用。

    Args:
        data: 消息字典。

    Returns:
        tuple: (text, MessageObject | None, suggestions | None, images | None)。
        列表均为拷贝，避免外部引用被改。
    """
    data = data or {}
    # 1. 取文本（None 归一成空串）
    text = str(data.get("text") or "")
    # 2. 有 object 则还原成 MessageObject
    obj = data.get("object")
    object_ = MessageObject.from_dict(obj) if obj else None
    # 3. 建议词：有才拷贝一份
    suggestions = list(data["suggestions"]) if data.get("suggestions") else None
    # 4. 图片 URL：有才拷贝
    images = list(data["images"]) if data.get("images") else None
    return text, object_, suggestions, images


@dataclass(slots=True)
class MessageObject:
    """业务对象卡片：设备 / 工单。

    用于用户点「发送设备 / 发送工单」，或机器人主动下发对象。
    attributes 保持开放字典，在 to_dict 时平铺到顶层，
    这样前端可以直接读 payload.device_id、payload.warranty_status。

    Attributes:
        type: 对象类型，"device" 或 "ticket"。
        id: 对象主键，如 DEV-2026-0001 / TKT-2026-000001。
        title: 卡片标题，如 "H3C LA2608"。
        attributes: 其余业务属性（model / status / warranty_status ...）。
    """

    type: str = "device"
    id: str = ""
    title: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端可直接消费的 dict。

        步骤：
            1. 写入三个固定字段 type / id / title。
            2. 把 attributes 平铺进顶层，前端免去嵌套取值。

        Returns:
            dict: {type, id, title, ...attributes}。
        """
        result: dict[str, Any] = {
            "type": self.type,
            "id": self.id,
            "title": self.title,
        }
        result.update(self.attributes)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MessageObject":
        """从 dict 还原 MessageObject。

        步骤：
            1. 取出 type / id / title（id 兼容 device_id / ticket_id 键名）。
            2. 其余键值全部收进 attributes，保持前向兼容。

        Args:
            data: 前端或历史记录里的 object 字典。

        Returns:
            MessageObject: 还原后的对象。
        """
        data = data or {}
        reserved = {"type", "id", "title"}
        attributes = {k: v for k, v in data.items() if k not in reserved}
        return cls(
            type=str(data.get("type") or "device"),
            id=str(data.get("id") or data.get("device_id") or data.get("ticket_id") or ""),
            title=str(data.get("title") or ""),
            attributes=attributes,
        )


@dataclass(slots=True)
class BotMessage:
    """机器人回复：文本、对象卡片、建议词、图片可任意组合。

    一轮对话里机器人可以连回多条，每条一个 BotMessage 实例。

    Attributes:
        text: 纯文本内容。
        object: 业务对象卡片，可选。
        suggestions: 建议词按钮，可选。
        images: 图片 URL 列表，手册截图等，前端渲染成图而非长链接。
    """

    text: str = ""
    object: Optional[MessageObject] = None
    suggestions: Optional[list[str]] = None
    images: Optional[list[str]] = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端消息字典。

        Returns:
            dict: {text, object?, suggestions?, images?}，内容部分交给 _dump_content。
        """
        return _dump_content(self.text, self.object, self.suggestions, self.images)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BotMessage":
        """从 dict 还原 BotMessage。

        Args:
            data: 消息字典。

        Returns:
            BotMessage: 还原后的机器人消息。
        """
        text, obj, suggestions, images = _load_content(data)
        return cls(text=text, object=obj, suggestions=suggestions, images=images)


ROLE_USER = "user"
ROLE_BOT = "bot"
ROLE_DIVIDER = "divider"


@dataclass(slots=True)
class Message:
    """对话流中的统一条目，覆盖用户消息、机器人消息、历史分隔线。

    落库 chat_messages 与出参 history 共用同一结构，避免两套模型互相转换。

    Attributes:
        role: 角色，取值见 ROLE_USER / ROLE_BOT / ROLE_DIVIDER。
        type: 消息类型枚举，序列化为字符串。
        text: 文本内容。
        object: 业务对象卡片，type=OBJECT 时使用。
        suggestions: 建议词，仅机器人消息使用。
    """

    role: str = ROLE_BOT
    type: MessageType = MessageType.TEXT
    text: str = ""
    object: Optional[MessageObject] = None
    suggestions: Optional[list[str]] = None
    images: Optional[list[str]] = None

    @classmethod
    def user_text(cls, text: str = "") -> "Message":
        """构造用户纯文本消息。

        Args:
            text: 文本内容。

        Returns:
            Message: role=user、type=TEXT 的消息。
        """
        return cls(role=ROLE_USER, type=MessageType.TEXT, text=text)

    @classmethod
    def user_object(cls, obj: MessageObject) -> "Message":
        """构造用户发送的业务对象卡片。

        Args:
            obj: 设备或工单对象。

        Returns:
            Message: role=user、type=OBJECT 的消息。
        """
        return cls(role=ROLE_USER, type=MessageType.OBJECT, object=obj)

    @classmethod
    def bot_text(
        cls,
        text: str,
        suggestions: Optional[list[str]] = None,
        images: Optional[list[str]] = None,
    ) -> "Message":
        """构造机器人纯文本回复（可附建议词与图片）。

        Args:
            text: 文本内容。
            suggestions: 建议词列表，可选。
            images: 图片 URL 列表，可选。

        Returns:
            Message: role=bot、type=TEXT 的消息。
        """
        return cls(
            role=ROLE_BOT,
            type=MessageType.TEXT,
            text=text,
            suggestions=suggestions,
            images=images,
        )

    @classmethod
    def bot_object(cls, obj: MessageObject, text: str = "") -> "Message":
        """构造机器人下发的业务对象卡片。

        Args:
            obj: 设备或工单对象。
            text: 卡片附带文案，可选。

        Returns:
            Message: role=bot、type=OBJECT 的消息。
        """
        return cls(role=ROLE_BOT, type=MessageType.OBJECT, text=text, object=obj)

    @classmethod
    def divider(cls, text: str = "以上为历史消息") -> "Message":
        """构造历史消息分隔线。

        Args:
            text: 分隔线文案。

        Returns:
            Message: role=divider、type=DIVIDER 的消息。
        """
        return cls(role=ROLE_DIVIDER, type=MessageType.DIVIDER, text=text)

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端 history / chat 出参格式。

        步骤：
            1. 写入 role 与 type.value（枚举转字符串）。
            2. 内容三件套交给公共 _dump_content，与 BotMessage 同源。

        Returns:
            dict: 前端可直接消费的消息字典。
        """
        # 1. 本类专属：role / type.value
        result: dict[str, Any] = {
            "role": self.role,
            "type": self.type.value,
        }
        # 2. 公共内容字段
        result.update(_dump_content(self.text, self.object, self.suggestions, self.images))
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """从 dict 或数据库 payload 还原 Message。

        步骤：
            1. role 做白名单校验，非法值兜底成 bot，防止脏数据带崩前端渲染。
            2. type 字符串经 MessageType.from_value 还原成枚举。
            3. type 缺省时按有无 object 判断 TEXT / OBJECT。
            4. 内容三件套交给公共 _load_content。

        Args:
            data: 消息字典。

        Returns:
            Message: 还原后的消息。
        """
        data = data or {}
        # 1. role 白名单
        role = data.get("role") or ROLE_BOT
        if role not in (ROLE_USER, ROLE_BOT, ROLE_DIVIDER):
            role = ROLE_BOT

        # 2. 字符串 → 枚举
        msg_type = MessageType.from_value(data.get("type") or "")

        # 3. type 缺省时按有无 object 兜底
        if not data.get("type"):
            msg_type = MessageType.OBJECT if data.get("object") else MessageType.TEXT

        # 4. 公共内容字段
        text, obj, suggestions, images = _load_content(data)
        return cls(
            role=role,
            type=msg_type,
            text=text,
            object=obj,
            suggestions=suggestions,
            images=images,
        )


@dataclass(slots=True)
class ProcessResult:
    """引擎处理一轮对话后的出参。

    service 层拿到它以后转成 ChatResponse.messages 返回给前端；
    支持链式追加，方便在处理器里连续组装多条回复。

    Attributes:
        messages: 本轮机器人要说的话，可多条。
        task_status: 当前任务状态，如 NEW / COLLECTING_SLOTS，可选。
        error: 错误提示，非空时前端红条展示，可选。
    """

    messages: list[BotMessage] = field(default_factory=list)
    task_status: Optional[str] = None
    error: Optional[str] = None

    def append_text(
        self,
        text: str,
        suggestions: Optional[list[str]] = None,
        images: Optional[list[str]] = None,
    ) -> "ProcessResult":
        """追加一条文本回复（链式调用，可附图片）。

        Args:
            text: 文本内容。
            suggestions: 建议词列表，可选。
            images: 图片 URL 列表，可选（手册截图等）。

        Returns:
            ProcessResult: 自身，支持继续链式调用。
        """
        self.messages.append(BotMessage(text=text, suggestions=suggestions, images=images))
        return self

    def append_object(self, obj: MessageObject, text: str = "") -> "ProcessResult":
        """追加一条对象卡片回复（链式调用）。

        Args:
            obj: 设备或工单对象。
            text: 卡片附带文案，可选。

        Returns:
            ProcessResult: 自身。
        """
        self.messages.append(BotMessage(text=text, object=obj))
        return self

    def to_dict(self) -> dict[str, Any]:
        """序列化为 ChatResponse 出参。

        步骤：
            1. messages 逐条调用 to_dict。
            2. task_status / error 仅在非空时带上，保持出参干净。

        Returns:
            dict: {messages: [...], task_status?: ..., error?: ...}。
        """
        result: dict[str, Any] = {
            "messages": [m.to_dict() for m in self.messages],
        }
        if self.task_status:
            result["task_status"] = self.task_status
        if self.error:
            result["error"] = self.error
        return result


if __name__ == "__main__":
    """自测：构造一轮真实对话，验证 to_dict / from_dict 往返一致。"""

    # 1. 用户发文本
    user_msg = Message.user_text("DEV-2026-0001 还在保修期吗？")

    # 2. 机器人回文本 + 建议词
    bot_msg = Message.bot_text(
        "设备 DEV-2026-0001 仍在保修期内。",
        suggestions=["查看维修进度", "转人工"],
    )

    # 3. 机器人下发设备卡片
    device = MessageObject(
        type="device",
        id="DEV-2026-0001",
        title="H3C LA2608",
        attributes={"model": "H3C LA2608", "warranty_status": "in_warranty"},
    )
    obj_msg = Message.bot_object(device)

    # 4. Message 往返
    for m in (user_msg, bot_msg, obj_msg):
        d = m.to_dict()
        back = Message.from_dict(d)
        assert back.role == m.role and back.type == m.type, "Message 往返失败"
        print(d)

    # 5. BotMessage 往返（验证公共序列化函数两边通用）
    bm = BotMessage(text="你好", object=device, suggestions=["报修"])
    bm2 = BotMessage.from_dict(bm.to_dict())
    assert bm2.to_dict() == bm.to_dict(), "BotMessage 往返失败"

    # 6. ProcessResult 链式组装
    result = (
        ProcessResult(task_status="COLLECTING_SLOTS")
        .append_text("正在为您查询保修信息...")
        .append_object(device, text="这是您的设备")
    )
    print(result.to_dict())
    print("messages 模型自测通过 ✓")
