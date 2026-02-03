"""Cursor adapter for hook translation.

This adapter translates between Cursor's hook format (which matches Claude Code)
and the unified HookEvent/HookResponse models.
"""

from gobby.adapters.claude_code import ClaudeCodeAdapter
from gobby.hooks.events import SessionSource


class CursorAdapter(ClaudeCodeAdapter):
    """Adapter for Cursor CLI hook translation."""

    source = SessionSource.CURSOR
