"""设备维修中台 FastAPI 应用装配。

安全边界（本地演示）：
    1. CORS 只允许前端源，禁止通配 origin 与 credentials 同时使用。
    2. 若配置 AGENT_API_KEY，则校验 X-Agent-Key 服务间认证头（常量时间比较）。
    3. 该密钥只认证 Agent 服务，不替代终端用户授权。
"""

from __future__ import annotations

import hmac
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.config import settings


openapi_tags = [
    {"name": "系统", "description": "服务可用性与基础检查接口。"},
    {"name": "Agent", "description": "Agent 工具注册表与对接元信息。"},
    {"name": "客户", "description": "查询客户名下设备列表与工单列表。"},
    {"name": "设备", "description": "设备档案、保修查询、设备历史事件。"},
    {"name": "工单", "description": "售后工单创建、更新、取消、状态与维修进度。"},
    {"name": "转人工", "description": "人工客服转接记录。"},
    {"name": "知识", "description": "设备手册检索（预留 RAG 对接）。"},
]


app = FastAPI(
    title="设备维修中台 Device Service",
    version="0.1.0",
    description=(
        "面向设备售后协同智能体（DeviceCare Agent）的业务中台。"
        "提供设备档案、保修查询、售后工单、维修进度、转人工与手册检索能力。"
        "LLM 只做理解与规划，确定性读写由本中台完成。"
    ),
    openapi_tags=openapi_tags,
)

# 开发/演示默认源；部署时用 DEVICE_CORS_ORIGINS 逗号分隔覆盖
_default_origins = ["http://127.0.0.1:5173", "http://localhost:5173"]
_origins_raw = os.getenv("DEVICE_CORS_ORIGINS", "")
allow_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()] or _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def agent_api_key_middleware(request: Request, call_next):
    """可选的服务间认证：配置了 AGENT_API_KEY 时校验请求头。

    步骤：
        1. 未配置密钥则直接放行（本地演示模式）。
        2. /health 免鉴权，便于探活。
        3. 常量时间比较 X-Agent-Key，失败返回 401，不打印密钥。

    Args:
        request: HTTP 请求。
        call_next: 后续处理。

    Returns:
        响应；密钥配置且不匹配时 401。
    """
    expected = settings.agent_api_key
    if not expected:
        return await call_next(request)
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)
    provided = request.headers.get("X-Agent-Key", "")
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


app.include_router(router)
