"""
Internal MCP tools for Gobby Session System.

This module provides backward compatibility by re-exporting from the
sessions package. New code should import directly from:
    from gobby.mcp_proxy.tools.sessions import create_session_messages_registry

Exposes functionality for:
- Session CRUD Operations
- Session Message Retrieval
- Message Search (FTS)
- Handoff Context Management

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from __future__ import annotations

# Re-export from sessions package for backward compatibility
from gobby.mcp_proxy.tools.sessions._factory import create_session_messages_registry
from gobby.mcp_proxy.tools.sessions._handoff import (
    _format_handoff_markdown,
    _format_turns_for_llm,
)

__all__ = ["create_session_messages_registry", "_format_handoff_markdown", "_format_turns_for_llm"]
