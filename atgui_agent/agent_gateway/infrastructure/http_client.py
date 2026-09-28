"""HTTP 客户端基础设施：调用设备维修中台与手册 RAG 服务。

职责：
    1. 创建并缓存 httpx.AsyncClient。
    2. 提供带错误处理的 GET / POST 封装。
    3. 提供 close_http_client()，进程退出前释放连接池。

设计要点：
    1. 配置一律走 get_settings()，本模块不读 .env。
    2. 默认客户端指向中台；RAG 用独立的 get_rag_client()。
    3. 只做传输层，不写保修/工单等业务语义。
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from agent_gateway.config.config import get_settings


_device_client: Optional[httpx.AsyncClient] = None
_rag_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """获取并缓存设备维修中台的异步 HTTP 客户端。

    进程内单例，避免每次请求都新建连接池。

    Returns:
        httpx.AsyncClient: 已绑定中台 base_url 的客户端。
    """
    global _device_client
    # 1. 单例已存在则直接返回
    if _device_client is None or _device_client.is_closed:
        cfg = get_settings().device_api
        _device_client = httpx.AsyncClient(
            base_url=cfg.base_url.rstrip("/"),
            timeout=httpx.Timeout(cfg.timeout_seconds),
            headers={"Accept": "application/json"},
        )
    return _device_client


def get_rag_client() -> httpx.AsyncClient:
    """获取并缓存手册 RAG 服务的异步 HTTP 客户端。

    Returns:
        httpx.AsyncClient: 已绑定 RAG base_url 的客户端。
    """
    global _rag_client
    # 1. 单例已存在则直接返回
    if _rag_client is None or _rag_client.is_closed:
        cfg = get_settings().rag
        _rag_client = httpx.AsyncClient(
            base_url=cfg.base_url.rstrip("/"),
            timeout=httpx.Timeout(cfg.timeout_seconds),
            headers={"Accept": "application/json"},
        )
    return _rag_client


async def close_http_client() -> None:
    """关闭所有 HTTP 客户端并释放连接池。

    建议在应用关停钩子（lifespan shutdown）里调用一次。

    Returns:
        None
    """
    global _device_client, _rag_client
    # 1. 中台客户端
    if _device_client is not None and not _device_client.is_closed:
        await _device_client.aclose()
    _device_client = None
    # 2. RAG 客户端
    if _rag_client is not None and not _rag_client.is_closed:
        await _rag_client.aclose()
    _rag_client = None


async def request_json(
    method: str,
    path: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
    json_body: Any = None,
    params: Optional[dict[str, Any]] = None,
    expected_status: tuple[int, ...] = (200,),
) -> dict[str, Any]:
    """发送 HTTP 请求并解析 JSON 响应。

    统一处理网络错误与非预期状态码，调用方只关心业务字段。

    Args:
        method: HTTP 方法，如 GET / POST。
        path: 相对路径，如 /devices/DEV-2026-0001/warranty。
        client: 自定义客户端；缺省用中台客户端。
        json_body: 请求体，POST / PUT 时使用。
        params: 查询参数。
        expected_status: 视作成功的状态码集合。

    Returns:
        dict: 响应 JSON；空响应体返回 {}。

    Raises:
        RuntimeError: 网络失败、状态码不符合预期，或响应不是 JSON。
    """
    http = client or get_http_client()
    # 1. 发送请求，网络层错误统一包装
    try:
        response = await http.request(
            method.upper(),
            path,
            json=json_body,
            params=params,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"请求 {method} {path} 失败：{exc}") from exc

    # 2. 状态码校验
    if response.status_code not in expected_status:
        raise RuntimeError(
            f"请求 {method} {path} 返回 HTTP {response.status_code}：{response.text[:200]}"
        )

    # 3. JSON 解析
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"响应不是 JSON：{response.text[:200]}") from exc
    return data if isinstance(data, dict) else {"data": data}


async def get_json(path: str, **kwargs: Any) -> dict[str, Any]:
    """GET 封装，等价 request_json("GET", ...)。

    Args:
        path: 相对路径。
        kwargs: 透传给 request_json。

    Returns:
        dict: 响应 JSON。
    """
    return await request_json("GET", path, **kwargs)


async def post_json(path: str, json_body: Any = None, **kwargs: Any) -> dict[str, Any]:
    """POST 封装，等价 request_json("POST", ...)。

    Args:
        path: 相对路径。
        json_body: 请求体。
        kwargs: 透传给 request_json。

    Returns:
        dict: 响应 JSON。
    """
    return await request_json("POST", path, json_body=json_body, **kwargs)


async def _smoke_test() -> None:
    """冒烟测试：初始化客户端 → 调中台 /health → 关闭客户端。

    步骤：
        1. 打印将要连接的 base_url。
        2. GET /health 并打印结果。
        3. finally 中务必 close_http_client()，避免连接泄漏。
    """
    import json

    cfg = get_settings().device_api
    print(f"[1] 初始化客户端 → {cfg.base_url}")

    client = get_http_client()
    print(f"[2] 客户端已创建: {type(client).__name__}, is_closed={client.is_closed}")

    try:
        result = await get_json("/health")
        print(f"[3] GET /health 成功: {json.dumps(result, ensure_ascii=False)}")
    except RuntimeError as exc:
        print(f"[3] GET /health 失败（中台未启动时属正常）: {exc}")
    finally:
        await close_http_client()
        print("[4] 客户端已关闭")


if __name__ == "__main__":
    """运行：python -m agent_gateway.infrastructure.http_client"""
    import asyncio

    asyncio.run(_smoke_test())
