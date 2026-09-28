"""全局统一配置：LLM、设备中台、数据库、RAG 与服务监听参数。

职责：
    1. 集中定义 Agent 网关所需的全部配置项。
    2. 从 atgui_agent/.env 与系统环境变量读取，代码内不写死密钥与 URL。
    3. 对外提供 get_settings() 单例，供 infrastructure / api / engine 引用。

设计要点：
    1. 全项目只在此处读 .env，其他模块一律 from agent_gateway.config.config import get_settings。
    2. 字段名与 .env 键一一对应（LLM_MODEL → llm_model）。
    3. 密钥类字段用 SecretStr，打印时必须经 safe_dump() 脱敏。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# 1. 定位并加载 .env
# ---------------------------------------------------------------------------
# 步骤：
#   1.1 计算路径：agent_gateway/ 与 上级 atgui_agent/
#   1.2 先加载 agent_gateway/.env（本地调试可覆盖）
#   1.3 再加载 atgui_agent/.env（统一配置位置）
#   1.4 override=False：已存在的系统环境变量优先，不被文件覆盖
# ---------------------------------------------------------------------------
_GATEWAY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PROJECT_ENV = os.path.abspath(os.path.join(_GATEWAY_ROOT, "..", ".env"))

load_dotenv(dotenv_path=os.path.join(_GATEWAY_ROOT, ".env"), override=False)
load_dotenv(dotenv_path=_PROJECT_ENV, override=False)


class LLMConfig(BaseModel):
    """大模型连接与采样参数（OpenAI 兼容协议）。

    Attributes:
        model: 模型名。
        base_url: OpenAI 兼容 Base URL。
        api_key: API Key，禁止落盘明文日志。
        temperature: 采样温度，规划/工具场景建议低温。
        max_tokens: 单次回复最大 token。
        timeout_seconds: 单次请求超时秒数。
    """

    model: str = Field(default="qwen-plus", description="模型名")
    base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="OpenAI 兼容 Base URL",
    )
    api_key: SecretStr = Field(default=SecretStr(""), description="API Key")
    temperature: float = Field(default=0.2, description="规划/工具场景建议低温")
    max_tokens: int = Field(default=2048, description="单次回复最大 token")
    timeout_seconds: float = Field(default=60.0, description="单次请求超时（秒）")

    def api_key_str(self) -> str:
        """取出真实 Key 字符串，仅在构造客户端时使用。

        Returns:
            str: 解密后的 API Key。
        """
        return self.api_key.get_secret_value()


class DeviceApiConfig(BaseModel):
    """设备维修中台 HTTP 配置。

    Attributes:
        base_url: 中台 Base URL，与前端代理保持一致。
        timeout_seconds: 请求超时秒数。
    """

    base_url: str = Field(
        default="http://192.168.10.15:18082",
        description="中台 Base URL",
    )
    timeout_seconds: float = Field(default=15.0, description="中台请求超时（秒）")


class DatabaseConfig(BaseModel):
    """对话状态与任务持久化数据库配置。

    Attributes:
        url: SQLAlchemy 连接串。
    """

    url: SecretStr = Field(
        default=SecretStr(""),
        description="SQLAlchemy 连接串，如 mysql+aiomysql://user:pass@host/db",
    )

    def url_str(self) -> str:
        """取出真实连接串。

        Returns:
            str: 解密后的 DATABASE_URL。
        """
        return self.url.get_secret_value()


class RAGConfig(BaseModel):
    """手册知识库服务配置。

    Attributes:
        base_url: RAG 服务地址。
        timeout_seconds: 请求超时秒数。
    """

    base_url: str = Field(default="http://192.168.10.15:8001", description="RAG 服务地址")
    timeout_seconds: float = Field(default=30.0, description="RAG 请求超时（秒）")


class AppConfig(BaseModel):
    """Agent 网关自身监听配置。

    Attributes:
        host: 监听地址。
        port: 监听端口，前端 /api 代理指向此处。
        debug: 是否开启调试日志。
    """

    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=8100, description="监听端口")
    debug: bool = Field(default=False, description="是否开启调试日志")


class Settings(BaseSettings):
    """全局设置根对象：扁平环境变量 → 分组配置。

    扁平字段与 .env 键名对应，由 pydantic-settings 自动映射；
    llm / device_api 等分组通过 property 组装，便于单测替换。

    Attributes:
        llm_model: 模型名。
        llm_base_url: 模型接口地址。
        llm_api_key: 模型 API Key。
        llm_temperature: 采样温度。
        llm_max_tokens: 最大 token。
        llm_timeout_seconds: 请求超时。
        device_api_base_url: 中台地址。
        device_api_timeout_seconds: 中台超时。
        database_url: 数据库连接串。
        rag_base_url: RAG 地址。
        rag_timeout_seconds: RAG 超时。
        app_host: 服务监听地址。
        app_port: 服务监听端口。
        app_debug: 调试开关。
        openai_api_key: 兼容 langchain 的备用 Key。
        openai_api_base: 兼容 langchain 的备用地址。
    """

    llm_model: str = Field(default="qwen-plus", validation_alias="LLM_MODEL")
    llm_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        validation_alias="LLM_BASE_URL",
    )
    llm_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="LLM_API_KEY")
    llm_temperature: float = Field(default=0.2, validation_alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, validation_alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: float = Field(default=60.0, validation_alias="LLM_TIMEOUT_SECONDS")

    device_api_base_url: str = Field(
        default="http://192.168.10.15:18082",
        validation_alias="DEVICE_API_BASE_URL",
    )
    device_api_timeout_seconds: float = Field(
        default=15.0, validation_alias="DEVICE_API_TIMEOUT_SECONDS"
    )

    database_url: SecretStr = Field(default=SecretStr(""), validation_alias="DATABASE_URL")

    rag_base_url: str = Field(
        default="http://192.168.10.15:8001", validation_alias="RAG_BASE_URL"
    )
    rag_timeout_seconds: float = Field(default=30.0, validation_alias="RAG_TIMEOUT_SECONDS")

    app_host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    app_port: int = Field(default=8100, validation_alias="APP_PORT")
    app_debug: bool = Field(default=False, validation_alias="APP_DEBUG")

    openai_api_key: Optional[SecretStr] = Field(
        default=None, validation_alias="OPENAI_API_KEY"
    )
    openai_api_base: Optional[str] = Field(default=None, validation_alias="OPENAI_API_BASE")

    model_config = SettingsConfigDict(
        env_file=(_PROJECT_ENV, os.path.join(_GATEWAY_ROOT, ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def llm(self) -> LLMConfig:
        """组装 LLM 配置。

        步骤：
            1. 优先取 LLM_API_KEY，为空则回退 OPENAI_API_KEY。
            2. base_url 同理回退 OPENAI_API_BASE。

        Returns:
            LLMConfig: 模型连接与采样参数。
        """
        api_key = self.llm_api_key
        if not api_key.get_secret_value() and self.openai_api_key:
            api_key = self.openai_api_key
        base_url = self.llm_base_url
        if not base_url and self.openai_api_base:
            base_url = self.openai_api_base
        return LLMConfig(
            model=self.llm_model,
            base_url=base_url,
            api_key=api_key,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
            timeout_seconds=self.llm_timeout_seconds,
        )

    @property
    def device_api(self) -> DeviceApiConfig:
        """组装设备中台配置。

        Returns:
            DeviceApiConfig: 中台连接参数。
        """
        return DeviceApiConfig(
            base_url=self.device_api_base_url,
            timeout_seconds=self.device_api_timeout_seconds,
        )

    @property
    def database(self) -> DatabaseConfig:
        """组装数据库配置。

        Returns:
            DatabaseConfig: 数据库连接参数。
        """
        return DatabaseConfig(url=self.database_url)

    @property
    def rag(self) -> RAGConfig:
        """组装 RAG 配置。

        Returns:
            RAGConfig: 知识库连接参数。
        """
        return RAGConfig(base_url=self.rag_base_url, timeout_seconds=self.rag_timeout_seconds)

    @property
    def app(self) -> AppConfig:
        """组装服务监听配置。

        Returns:
            AppConfig: host / port / debug。
        """
        return AppConfig(host=self.app_host, port=self.app_port, debug=self.app_debug)

    def safe_dump(self) -> dict:
        """导出可安全打印的配置字典，密钥脱敏。

        步骤：
            1. 取各分组字段。
            2. api_key / database.url 只保留前 4 位 + ***。

        Returns:
            dict: 脱敏后的配置快照。
        """
        def mask(secret: SecretStr) -> str:
            raw = secret.get_secret_value()
            return (raw[:4] + "***") if raw else "(empty)"

        return {
            "llm": {
                "model": self.llm.model,
                "base_url": self.llm.base_url,
                "api_key": mask(self.llm.api_key),
                "temperature": self.llm.temperature,
            },
            "device_api": {"base_url": self.device_api.base_url},
            "database": {"url": mask(self.database.url)},
            "rag": {"base_url": self.rag.base_url},
            "app": {"host": self.app.host, "port": self.app.port},
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。

    首次调用触发 .env 读取，之后共享同一实例，零额外 IO。

    Returns:
        Settings: 全局配置对象。
    """
    return Settings()


if __name__ == "__main__":
    """冒烟测试：打印脱敏配置。"""
    import json

    print(json.dumps(get_settings().safe_dump(), ensure_ascii=False, indent=2))
