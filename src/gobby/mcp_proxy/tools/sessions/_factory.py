"""Factory function for creating the session messages tool registry.

Orchestrates the creation of all session tool sub-registries and merges them
into a unified registry.

Note: This is a transitional module. During the Strangler Fig migration,
it re-exports from the original session_messages.py. Once all tools are
extracted to their own modules, this will become the canonical factory.
"""

# Transitional: re-export from original module until extraction is complete
from gobby.mcp_proxy.tools.session_messages import create_session_messages_registry

__all__ = ["create_session_messages_registry"]
