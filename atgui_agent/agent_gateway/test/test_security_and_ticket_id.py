"""中台安全与工单号测试（不依赖真实数据库）。

覆盖：
    1. AGENT_API_KEY 中间件：配置后无头拒绝、正确头放行、health 免鉴权。
    2. _next_ticket_id 并发语义：基于最大序号而非 count()。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_agent_api_key_enforced(monkeypatch) -> None:
    """配置 AGENT_API_KEY 后，缺少/错误请求头应 401，正确头 200。"""
    import importlib

    monkeypatch.setenv("AGENT_API_KEY", "test-secret")

    import app.config as config_module
    importlib.reload(config_module)
    import app.app as app_module
    importlib.reload(app_module)

    # health 会查库：注入假 get_db，避免测试依赖 MySQL
    class _FakeDB:
        def execute(self, *args, **kwargs):
            return None

    from app.database import get_db

    app_module.app.dependency_overrides[get_db] = lambda: _FakeDB()

    client = TestClient(app_module.app)

    # health 免鉴权
    assert client.get("/health").status_code == 200
    # 无头
    assert client.get("/tools").status_code == 401
    # 错误头
    assert client.get("/tools", headers={"X-Agent-Key": "wrong"}).status_code == 401
    # 正确头
    assert client.get("/tools", headers={"X-Agent-Key": "test-secret"}).status_code == 200

    app_module.app.dependency_overrides.clear()
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    importlib.reload(config_module)
    importlib.reload(app_module)


def test_next_ticket_id_uses_max_not_count() -> None:
    """工单号取最大序号 +1，即使存在空洞也不会与旧号重复。"""

    class _FakeQuery:
        def __init__(self, value):
            self._value = value

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return self._value

    class _FakeDB:
        def __init__(self, value):
            self._value = value

        def query(self, *args, **kwargs):
            return _FakeQuery(self._value)

    from datetime import datetime

    from app.api import _next_ticket_id

    year = datetime.now().year
    # 即使 count=2，最大号是 5，新号必须是 6
    db = _FakeDB((f"TKT-{year}-000005",))
    assert _next_ticket_id(db) == f"TKT-{year}-000006"

    # 空表
    db_empty = _FakeDB(None)
    assert _next_ticket_id(db_empty) == f"TKT-{year}-000001"
