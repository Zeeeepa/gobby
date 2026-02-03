"""Copilot adapter for hook translation.

This adapter translates between Copilot's hook format (which matches Claude Code)
and the unified HookEvent/HookResponse models.
"""

from gobby.adapters.claude_code import ClaudeCodeAdapter
from gobby.hooks.events import SessionSource


class CopilotAdapter(ClaudeCodeAdapter):
    """Adapter for Copilot CLI hook translation."""

    source = SessionSource.COPILOT
