"""
MCP routes package.

Decomposed from monolithic mcp.py using Strangler Fig pattern.
Each router is now in its own focused module:
- tools.py: create_mcp_router (tool discovery, execution, search)
- code.py: create_code_router (code execution, dataset processing)
- hooks.py: create_hooks_router (CLI hook adapter)
- plugins.py: create_plugins_router (plugin management)
- webhooks.py: create_webhooks_router (webhook management)

This __init__.py re-exports all routers for backward compatibility.
"""

from gobby.servers.routes.mcp.code import create_code_router
from gobby.servers.routes.mcp.hooks import create_hooks_router
from gobby.servers.routes.mcp.plugins import create_plugins_router
from gobby.servers.routes.mcp.tools import create_mcp_router
from gobby.servers.routes.mcp.webhooks import create_webhooks_router

__all__ = [
    "create_code_router",
    "create_hooks_router",
    "create_mcp_router",
    "create_plugins_router",
    "create_webhooks_router",
]
