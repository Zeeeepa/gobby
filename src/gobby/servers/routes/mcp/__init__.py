"""
MCP routes package.

Re-exports routers for backward compatibility during Strangler Fig migration.
Routers are being extracted from base.py into focused sub-modules.
"""

from gobby.servers.routes.mcp.base import (
    create_code_router,
    create_hooks_router,
    create_mcp_router,
    create_plugins_router,
)
from gobby.servers.routes.mcp.webhooks import create_webhooks_router

__all__ = [
    "create_code_router",
    "create_hooks_router",
    "create_mcp_router",
    "create_plugins_router",
    "create_webhooks_router",
]
