"""
Server management endpoints for MCP server lifecycle.

Target endpoints to migrate from tools.py:
- POST /servers (line 643) - add_mcp_server
- POST /servers/import (line 724) - import_mcp_server
- DELETE /servers/{name} (line 815) - remove_mcp_server
- POST /refresh (line 1307) - refresh_mcp_connections

Importer analysis:
- These are nested route handlers inside create_mcp_router()
- No external modules import these handlers directly
- Migration: Extract as standalone async functions, register in router factory

Dependencies:
- FastAPI: APIRouter, Depends, HTTPException
- gobby.servers.routes.dependencies: get_mcp_manager, get_server
- gobby.utils.metrics: get_metrics_collector
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Placeholder - handlers will be migrated from tools.py in Phase 3
__all__: list[str] = []
