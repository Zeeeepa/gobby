"""
Discovery endpoints for MCP tool and server listing.

Target endpoints to migrate from tools.py:
- GET /{server_name}/tools (line 118) - list_mcp_tools
- GET /servers (line 248) - list_mcp_servers
- GET /tools (line 310) - list_all_mcp_tools
- POST /tools/schema (line 439) - get_tool_schema
- GET /status (line 1105) - mcp_status

Importer analysis:
- These are nested route handlers inside create_mcp_router()
- No external modules import these handlers directly
- Migration: Extract as standalone async functions, register in router factory

Dependencies:
- FastAPI: APIRouter, Depends, HTTPException
- gobby.servers.routes.dependencies: get_internal_manager, get_mcp_manager
- gobby.utils.metrics: get_metrics_collector
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Placeholder - handlers will be migrated from tools.py in Phase 3
__all__: list[str] = []
