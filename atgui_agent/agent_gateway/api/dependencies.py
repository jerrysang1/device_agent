"""API 依赖装配：仓储与中台客户端的注入点。

测试通过 monkeypatch 替换 get_state_repository / get_device_client，
因此默认实现可以走真实数据库与 HTTP，而测试不需要外部服务。
"""

from __future__ import annotations

from typing import Any

from agent_gateway.repository.state_repository import get_state_repository as _get_state_repository
from agent_gateway.infrastructure.http_client import get_json as _get_json, post_json as _post_json


class DeviceClientProtocol:
    """中台客户端的最小协议（便于测试替身实现）。"""

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def post_json(self, path: str, json_body: Any = None, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError


class HttpDeviceClient(DeviceClientProtocol):
    """真实实现：走 infrastructure.http_client。"""

    async def get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return await _get_json(path, **kwargs)

    async def post_json(self, path: str, json_body: Any = None, **kwargs: Any) -> dict[str, Any]:
        return await _post_json(path, json_body=json_body, **kwargs)


def get_state_repository():
    """获取状态仓储（默认走数据库实现）。"""
    return _get_state_repository()


def get_device_client() -> DeviceClientProtocol:
    """获取中台客户端。"""
    return HttpDeviceClient()
