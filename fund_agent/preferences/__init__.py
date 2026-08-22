"""投资者偏好域（与 fund/ 平级的新域，Slice P1：flomo-import）。

提供 Flomo HTML 导出解析（flomo_parser）与 SQLite 幂等存储（store）。
"""

from fund_agent.preferences.flomo_parser import (
    FlomoMemo,
    FlomoParseError,
    FlomoParseResult,
    parse_flomo_export,
    parse_flomo_html,
)
from fund_agent.preferences.store import (
    ImportResult,
    PreferencesStore,
    PreferencesStoreError,
    open_preferences_store,
)

__all__ = [
    "FlomoMemo",
    "FlomoParseError",
    "FlomoParseResult",
    "ImportResult",
    "PreferencesStore",
    "PreferencesStoreError",
    "open_preferences_store",
    "parse_flomo_export",
    "parse_flomo_html",
]
