"""HTTP 路由：health / chat / history。

只做协议转换，不写业务决策。
出参字段与前端 App.vue 对齐：chat/history 顶层含 messages。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_gateway.api import dependencies
from agent_gateway.api.schemas import ChatRequest, ChatResponse, HealthData, HistoryResponse
from agent_gateway.service.dialogue_service import DialogueService

router = APIRouter()


def get_dialogue_service(
    repo=Depends(dependencies.get_state_repository),
    device=Depends(dependencies.get_device_client),
) -> DialogueService:
    """装配对话服务。

    Args:
        repo: 状态仓储。
        device: 中台客户端。

    Returns:
        DialogueService: 服务实例。
    """
    return DialogueService(repository=repo, device_client=device)


@router.get("/health", tags=["系统"])
async def health() -> dict:
    """健康检查。

    Returns:
        dict: {code, message, data:{status, service}}。
    """
    return {"code": 0, "message": "ok", "data": HealthData().model_dump()}


@router.post("/api/chat", response_model=ChatResponse, tags=["对话"])
async def chat(
    body: ChatRequest,
    service: DialogueService = Depends(get_dialogue_service),
) -> ChatResponse:
    """处理一轮聊天，返回前端可直接渲染的 messages。

    Args:
        body: 聊天请求（sender_id + text）。
        service: 对话服务。

    Returns:
        ChatResponse: 顶层 messages / task_status。

    Raises:
        HTTPException: 参数非法或服务失败。
    """
    if not body.sender_id.strip():
        raise HTTPException(status_code=400, detail="sender_id 不能为空")
    text = (body.text or "").strip()
    object_data = body.object if isinstance(body.object, dict) else None
    # 为什么：点选设备/工单卡片时可能只有 object、没有 text
    if not text and not object_data:
        raise HTTPException(status_code=400, detail="text 不能为空")
    try:
        data = await service.chat(body.sender_id.strip(), text, user_object=object_data)
    except Exception as exc:  # 服务层已降级话术；这里兜底 500
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(**data)


@router.get("/api/chat/history", response_model=HistoryResponse, tags=["对话"])
async def history(
    sender_id: str = Query(..., min_length=1),
    service: DialogueService = Depends(get_dialogue_service),
) -> HistoryResponse:
    """读取历史消息。

    Args:
        sender_id: 用户ID。
        service: 对话服务。

    Returns:
        HistoryResponse: 顶层 messages。
    """
    messages = await service.history(sender_id.strip())
    return HistoryResponse(sender_id=sender_id, messages=messages)
