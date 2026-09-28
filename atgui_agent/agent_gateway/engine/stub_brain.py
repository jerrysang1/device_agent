"""确定性大脑入口：流程引擎优先，知识/闲聊兜底，不上 LLM。

职责：
    1. 有 DialogueState 时走 FlowExecutor（YAML 多轮流程）。
    2. 流程认不了的，走手册 RAG / 能力说明。
    3. 工具失败降级为可读话术，不抛裸异常给前端。

设计：
    1. 状态读写在 FlowExecutor + service 层；本文件只做分流。
    2. 保留知识问答，与任务流程解耦。
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from agent_gateway.chitchat.handler import reply as chitchat_reply
from agent_gateway.domain.messages import MessageObject, ProcessResult
from agent_gateway.domain.state import DialogueState
from agent_gateway.engine.flow_executor import get_flow_executor
from agent_gateway.infrastructure.http_client import get_rag_client
from agent_gateway.task.tools import ToolRegistry

# 手册截图等图片链接：从 RAG 正文抽出，改由前端 <img> 渲染
_IMAGE_URL_PATTERN = re.compile(
    r"https?://[^\s\"'<>]+?\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)
_IMAGE_MARKER_PATTERN = re.compile(r"【图片】|\[图片\]|!\[.*?\]\(.*?\)")

CAPABILITY_TIP = (
    "我可以帮您：查保修（提供设备编号如 DEV-2026-0001）、"
    "报修建工单、查维修进度、转人工、查询设备手册。"
)


async def handle_message(
    text: str,
    sender_id: str,
    device_client: Any,
    state: Optional[DialogueState] = None,
    user_object: Optional[dict[str, Any]] = None,
) -> ProcessResult:
    """处理一条用户文本/卡片，返回机器人回复并推进流程状态。

    步骤：
        1. 归一化文本。
        2. 纯卡片消息：收槽中则用编号填槽，否则记入 focused_object 并给引导。
        3. 优先交给 FlowExecutor（续任务 / 开新流程 / 收槽）。
        4. 流程不处理时：知识问答走 RAG，闲聊走 chitchat，其余给能力说明。

    Args:
        text: 用户文本。
        sender_id: 用户ID。
        device_client: 中台客户端（可注入替身）。
        state: 对话状态；缺省临时建一份（仅兜底，不持久化任务）。
        user_object: 用户点选的设备/工单卡片，可空。

    Returns:
        ProcessResult: 机器人消息列表。
    """
    raw = (text or "").strip()
    working_state = state if state is not None else DialogueState(sender_id=sender_id)
    executor = get_flow_executor(ToolRegistry(device_client))

    # 0. 纯卡片消息：收槽时当编号，否则聚焦对象
    if user_object and not raw:
        obj_id = _object_slot_text(user_object)
        if obj_id and working_state.task is not None:
            flow_result = await executor.handle(working_state, obj_id)
            if flow_result.messages:
                return flow_result
        return _focus_object(working_state, user_object)

    # 1. 流程引擎优先（保修/报修/进度/转人工 + 多轮收槽）
    flow_result = await executor.handle(working_state, raw)
    if flow_result.messages:
        return flow_result

    result = ProcessResult()
    if not raw:
        result.append_text(CAPABILITY_TIP)
        return result

    # 2. 知识问答：调手册 RAG，带引用；不可用时显式降级
    wants_knowledge = any(
        k in raw
        for k in ("手册", "说明书", "怎么配", "怎么设置", "怎么用", "怎么使用", "如何配置", "如何设置", "如何使用", "VLAN")
    )
    if wants_knowledge:
        return await _query_manual(raw, result)

    # 3. 闲聊：问候/客套/寒暄，避免冷冰冰的清单
    chitchat_text = chitchat_reply(raw)
    if chitchat_text:
        result.append_text(chitchat_text, suggestions=["查保修", "帮我报修", "转人工"])
        return result

    # 4. 兜底能力说明
    result.append_text(CAPABILITY_TIP, suggestions=["查保修", "帮我报修", "转人工"])
    return result


def _object_slot_text(user_object: dict[str, Any]) -> str:
    """从卡片里取出可填槽的编号（device_id / ticket_id）。"""
    attrs = user_object.get("attributes") or {}
    obj_id = (
        user_object.get("id")
        or user_object.get("device_id")
        or user_object.get("ticket_id")
        or attrs.get("device_id")
        or attrs.get("ticket_id")
        or ""
    )
    return str(obj_id).strip()


def _focus_object(state: DialogueState, user_object: dict[str, Any]) -> ProcessResult:
    """记录用户点选对象，并给出下一步意图引导。"""
    obj = MessageObject.from_dict(user_object)
    state.focused_object = obj
    result = ProcessResult()
    label = "设备" if obj.type == "device" else "工单"
    who = obj.id or obj.title or ""
    result.append_text(
        f"已选中{label} {who}。您可以说「查保修」「帮我报修」或「查进度」。",
        suggestions=["查保修", "帮我报修", "查进度"],
    )
    return result


async def _query_manual(query: str, result: ProcessResult) -> ProcessResult:
    """调用手册 RAG 检索，组装带引用的答案。

    步骤：
        1. POST {RAG}/query，is_stream=false，同步拿 answer + sources。
        2. 有引用则附在正文后；无命中则如实说明，不编造手册页码。
        3. 回复标注「手册知识库」与耗时，便于区分是不是走了 RAG。
        4. RAG 不可用时显式 not_configured，禁止伪造 PDF 引用。

    Args:
        query: 用户原始问题。
        result: 待填充的回复容器。

    Returns:
        ProcessResult: 填充后的回复。
    """
    # 1. 调 RAG（非流式），记录耗时
    started = time.perf_counter()
    try:
        rag = get_rag_client()
        resp = await rag.post("/query", json={"query": query, "is_stream": False})
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        result.append_text(
            "知识手册问答暂时不可用（not_configured）。"
            "您可以先问保修或报修；手册服务恢复后这里会给出带引用的答案。",
            suggestions=["查保修", "帮我报修", "转人工"],
        )
        return result
    elapsed = time.perf_counter() - started

    # 2. 兼容扁平返回与 {data: ...} 包装
    data = payload
    if isinstance(payload, dict) and "answer" not in payload and isinstance(payload.get("data"), dict):
        data = payload["data"]
    answer = (data.get("answer") or "").strip()
    sources = data.get("sources") or data.get("citations") or []

    # 3. 抽出图片 URL，正文里去掉长链接与【图片】占位，避免刷屏
    images = _extract_image_urls(answer)
    answer = _strip_image_noise(answer)

    if not answer:
        answer = "手册库中没有找到相关内容，请换个说法或提供具体型号。"

    if sources:
        lines = ["", "参考来源："]
        for i, item in enumerate(sources, start=1):
            if not isinstance(item, dict):
                continue
            title = item.get("file_title") or item.get("title") or "手册片段"
            page = item.get("page")
            page_text = f"（第 {page} 页）" if page else ""
            lines.append(f"{i}. {title}{page_text}")
        answer = answer + "\n".join(lines)

    # 4. 标注数据来源与耗时，方便核对是不是走了 RAG
    header = f"【手册知识库 · 检索 {elapsed:.1f}s】\n"
    result.append_text(
        header + answer,
        suggestions=["查保修", "帮我报修", "转人工"],
        images=images or None,
    )
    return result


def _extract_image_urls(text: str) -> list[str]:
    """从 RAG 正文抽出图片 URL，保序去重。

    Args:
        text: RAG 返回的 answer 原文。

    Returns:
        list[str]: 图片 URL 列表。
    """
    seen: set[str] = set()
    urls: list[str] = []
    for match in _IMAGE_URL_PATTERN.findall(text or ""):
        if match not in seen:
            seen.add(match)
            urls.append(match)
    return urls


def _strip_image_noise(text: str) -> str:
    """去掉正文里的图片 URL 与【图片】占位，压掉多余空行。

    Args:
        text: RAG 返回的 answer 原文。

    Returns:
        str: 适合阅读的纯文本。
    """
    cleaned = _IMAGE_URL_PATTERN.sub("", text or "")
    cleaned = _IMAGE_MARKER_PATTERN.sub("", cleaned)
    # 连续空行压成一行，去掉行尾多余空白
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
