"""
FastAPI route modules for Gobby HTTP server.

Each module contains an APIRouter with related endpoints.
"""

from gobby.servers.routes.admin import create_admin_router
from gobby.servers.routes.mcp import (
    create_hooks_router,
    create_mcp_router,
    create_plugins_router,
    create_webhooks_router,
)
from gobby.servers.routes.sessions import create_sessions_router

__all__ = [
    "create_admin_router",
    "create_hooks_router",
    "create_mcp_router",
    "create_plugins_router",
    "create_sessions_router",
    "create_webhooks_router",
]
