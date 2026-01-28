"""Factory function for creating the session messages tool registry.

Orchestrates the creation of all session tool sub-registries and merges them
into a unified registry.

Note: This is a transitional module. During the Strangler Fig migration,
it re-exports from the original session_messages.py. Once all tools are
extracted to their own modules, this will become the canonical factory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager

__all__ = ["create_session_messages_registry"]


def create_session_messages_registry(
    message_manager: LocalSessionMessageManager | None = None,
    session_manager: LocalSessionManager | None = None,
) -> InternalToolRegistry:
    """
    Create a sessions tool registry with session and message tools.

    This is a transitional wrapper that delegates to the original module.
    Once the full extraction is complete, this will become the canonical factory.

    Args:
        message_manager: LocalSessionMessageManager instance for message operations
        session_manager: LocalSessionManager instance for session CRUD

    Returns:
        InternalToolRegistry with all session tools registered
    """
    # Lazy import to avoid circular dependency
    from gobby.mcp_proxy.tools.session_messages import (
        create_session_messages_registry as _create_registry,
    )

    return _create_registry(message_manager, session_manager)
