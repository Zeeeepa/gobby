"""
Codex adapter implementations.

Target classes to migrate from codex.py:
- CodexAdapter: Main adapter for Codex CLI integration
- CodexNotifyAdapter: Notification adapter for hook events

Dependencies:
- gobby.adapters.base (BaseAdapter)
- gobby.adapters.codex_impl.client (CodexAppServerClient)
- gobby.adapters.codex_impl.types (type definitions)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Placeholder - adapters will be migrated from codex.py
__all__: list[str] = []
