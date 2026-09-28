"""pytest 路径配置：把 agent_gateway 与中台源码加入 sys.path。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "atgui_agent"))
sys.path.insert(0, str(ROOT / "device-service-backend"))
