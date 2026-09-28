"""Agent 网关 FastAPI 应用入口。

职责：
    1. 创建 app、注册路由、装配 CORS。
    2. lifespan：启动建表，关停释放 HTTP/DB 连接。
    3. 不写业务决策。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_gateway.api.routers import router
from agent_gateway.infrastructure.database import close_database, init_database
from agent_gateway.infrastructure.http_client import close_http_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    应用启停钩子。
    1. 回调lifespan的时机：在服务一启动的时候会先来调用（初始化HTTP客户端、Redis客户端、数据库连接）
    2. 服务一关停的时候会调用（释放HTTP客户端、Redis客户端、数据库连接）
    3. 参数app以及类型必须要指定，因为底层FastAPI会使用它来管理应用状态。
    4. yield 语句：让 FASTAPI 处理请求。。。

    步骤：
        1. 启动：init_database（探活 + 建表）。
        2. 关停：close_http_client / close_database。
    """
    await init_database()
    yield
    await close_http_client()
    await close_database()


def create_app() -> FastAPI:
    """构建 FastAPI 实例（便于测试装配替身后重建）。

    Returns:
        FastAPI: 已注册路由的应用。
    """
    app = FastAPI(
        title="设备售后 Agent 网关",
        version="0.1.0",
        lifespan=lifespan,
    )
    # 本地演示：只允许前端源；生产应收紧并禁止通配 + credentials
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()





import uvicorn

if __name__ == "__main__":
    # Debug 本文件 → 常驻服务；断点打在 routers/dialogue_service
    uvicorn.run("agent_gateway.api.app:app", host="127.0.0.1", port=8100)