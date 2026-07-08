"""AlphaWorkbench core utilities.

Settings 统一从 alpha_workbench.core.config 导出，避免重复定义。
"""

from __future__ import annotations

from alpha_workbench.core.config import Settings, settings

__all__ = ["Settings", "settings"]
