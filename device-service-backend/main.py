#!/usr/bin/env python3
"""
设备维修中台启动脚本
"""
from __future__ import annotations

import uvicorn

from app.config import settings


def main():
    """启动 FastAPI 应用"""
    print("🚀 正在启动设备维修中台 Device Service...")
    print(f"📍 地址: http://{settings.app_host}:{settings.app_port}")
    print(f"📚 API 文档: http://{settings.app_host}:{settings.app_port}/docs")

    uvicorn.run(
        "app.app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
