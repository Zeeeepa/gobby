"""Windsurf adapter for hook translation.

This adapter translates between Windsurf's hook format (which matches Claude Code)
and the unified HookEvent/HookResponse models.
"""

from gobby.adapters.claude_code import ClaudeCodeAdapter
from gobby.hooks.events import SessionSource


class WindsurfAdapter(ClaudeCodeAdapter):
    """Adapter for Windsurf CLI hook translation."""

    source = SessionSource.WINDSURF
