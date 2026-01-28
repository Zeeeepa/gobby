"""Session tools package.

This package provides MCP tools for session management. Re-exports maintain
backwards compatibility with the original session_messages.py module.

Public API:
    - create_session_messages_registry: Factory function to create the session tool registry
"""

from gobby.mcp_proxy.tools.sessions._factory import create_session_messages_registry

__all__ = [
    "create_session_messages_registry",
]
