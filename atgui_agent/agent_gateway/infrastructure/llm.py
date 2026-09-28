"""LLM 基础设施：创建聊天模型，提供文本补全与结构化 JSON 规划。

职责：
    1. 基于 config.config.get_settings() 创建并缓存 LangChain 聊天模型。
    2. 提供普通对话 complete / acomplete 与结构化规划 complete_json。
    3. 不在本模块读 .env —— 配置统一走 config.config。

设计要点：
    1. 只负责「怎么调大模型」，不写业务路由与工具逻辑。
    2. 上层通过 get_chat_model() 或 complete() 调用。
    3. 规划场景走 complete_json()，模型只出 JSON，是否执行由上层校验。
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agent_gateway.config.config import get_settings


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    """创建并缓存 LangChain 聊天模型实例。

    用 lru_cache 是为了避免每次对话都重新建连；配置在进程内不会变。

    步骤：
        1. 从 get_settings().llm 读取模型配置。
        2. 校验 api_key，未配置则抛出明确错误，而不是等到请求才 401。
        3. 构造 ChatOpenAI（OpenAI 兼容协议）。

    Returns:
        ChatOpenAI: 可直接 invoke / ainvoke 的模型对象。

    Raises:
        RuntimeError: 未配置 LLM_API_KEY 或 OPENAI_API_KEY。
    """
    llm_cfg = get_settings().llm
    api_key = llm_cfg.api_key_str()
    if not api_key:
        raise RuntimeError(
            "缺少 LLM_API_KEY（或 OPENAI_API_KEY）。"
            "请在 flow_config/.env 中配置后再启动。"
        )
    return ChatOpenAI(
        model=llm_cfg.model,
        api_key=api_key,
        base_url=llm_cfg.base_url,
        temperature=llm_cfg.temperature,
        max_tokens=llm_cfg.max_tokens,
        timeout=llm_cfg.timeout_seconds,
    )


def complete(messages: list[dict[str, str]] | str, **kwargs: Any) -> str:
    """普通文本补全：发消息，取回纯文本回复。

    Args:
        messages: 字符串表示单轮 user 消息；也可传 [{role, content}, ...] 多轮。
        kwargs: 透传给模型的覆盖参数，如 temperature。

    Returns:
        str: 剥掉首尾空白后的模型回复正文。
    """
    # 1. 字符串包装成单条 user 消息
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    model = get_chat_model()
    if kwargs:
        model = model.bind(**kwargs)
    # 2. 调用模型并取文本
    response = model.invoke(messages)
    return (response.text or "").strip()


async def acomplete(messages: list[dict[str, str]] | str) -> str:
    """异步文本补全，与 complete 等价，供异步路由使用。

    Args:
        messages: 同 complete。

    Returns:
        str: 模型回复正文。
    """
    # 1. 字符串包装成单条 user 消息
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    # 2. 异步调用
    response = await get_chat_model().ainvoke(messages)
    return (response.text or "").strip()


class TurnPlanDraft(BaseModel):
    """LLM 规划草稿：模型填字段，是否执行由上层校验。

    Attributes:
        route: 路由，knowledge / service / chitchat 三选一。
        task_type: 任务类型，如 create_service_ticket、check_warranty。
        slots: 已抽到的槽位。
        next_action: 下一步动作。
        reply: 面向用户的简短话术，可为空。
    """

    route: str = Field(description="knowledge | service | chitchat")
    task_type: str = Field(default="", description="任务类型标识")
    slots: dict[str, Any] = Field(default_factory=dict, description="已抽到的槽位")
    next_action: str = Field(
        default="reply",
        description="ask_missing_slots | ask_confirmation | call_tool | reply",
    )
    reply: str = Field(default="", description="对用户说的话")


def complete_json(
    prompt: str,
    *,
    schema: type[BaseModel] = TurnPlanDraft,
    **kwargs: Any,
) -> dict[str, Any]:
    """结构化补全：要求模型只输出 JSON，并解析为 dict。

    用在规划链路——模型只负责填字段，执行前还有 Validator 兜底，
    即使模型偶尔「说人话」也不会把脏计划直接跑掉。

    步骤：
        1. 在 prompt 末尾追加「只输出 JSON」的硬约束。
        2. 调用 complete() 拿到文本。
        3. 剥掉可能的 ```json 代码块围栏。
        4. 截取首个 { 到最后一个 } 后 json.loads。
        5. 补齐缺省字段，降低上层判空成本。

    Args:
        prompt: 完整提示词（系统规则 + 用户本轮消息 + 上下文）。
        schema: 目标结构，当前仅作文档与扩展位。
        kwargs: 透传给模型的覆盖参数。

    Returns:
        dict: 含 route / task_type / slots / next_action / reply 的规划草稿。

    Raises:
        ValueError: 模型输出不是合法 JSON，由上层降级为澄清话术。
    """
    _ = schema  # 预留：后续可换 with_structured_output

    hard_rule = (
        "\n\n【输出约束】只输出一个 JSON 对象，不要任何解释、不要 Markdown 代码块。"
        "字段必须包含：route, task_type, slots, next_action, reply。"
    )
    raw = complete(prompt + hard_rule, **kwargs)

    # 3.1 去掉 ```json ... ``` 围栏
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    # 3.2 截取首个 { 到最后一个 }，容忍模型多说一句话
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"LLM 未返回 JSON：{raw[:200]!r}")
    payload = json.loads(text[start : end + 1])

    # 3.3 补齐缺省字段
    return {
        "route": payload.get("route", ""),
        "task_type": payload.get("task_type", ""),
        "slots": payload.get("slots") or {},
        "next_action": payload.get("next_action", "reply"),
        "reply": payload.get("reply", ""),
    }


if __name__ == "__main__":
    """冒烟测试：打印脱敏配置，再调一次模型。"""

    print("模型配置:", get_settings().safe_dump()["llm"])
    print("回复:", complete("用一句话介绍设备售后助手可以做什么。"))
