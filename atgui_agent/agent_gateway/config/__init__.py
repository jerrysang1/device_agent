"""
config 包 —— 全局统一配置入口。

对外导出：
    get_settings / Settings
"""

from agent_gateway.config.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
