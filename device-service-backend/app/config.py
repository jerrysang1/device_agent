from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://device:Device.123@127.0.0.1:3306/device_service?charset=utf8mb4",
    )
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "18082"))
    # shopkeeper_brain 默认端口 8001：POST /query
    rag_base_url: str = os.getenv("RAG_BASE_URL", "http://127.0.0.1:8001")
    rag_timeout_seconds: float = float(os.getenv("RAG_TIMEOUT_SECONDS", "30"))
    agent_api_key: str = os.getenv("AGENT_API_KEY", "")


settings = Settings()
