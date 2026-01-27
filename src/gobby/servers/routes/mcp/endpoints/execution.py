"""
Execution endpoints for MCP tool invocation.

Target endpoints to migrate from tools.py:
- POST /tools/call (line 531) - call_mcp_tool
- POST /{server_name}/tools/{tool_name} (line 1166) - call_tool_by_path

Importer analysis:
- These are nested route handlers inside create_mcp_router()
- No external modules import these handlers directly
- Migration: Extract as standalone async functions, register in router factory

Dependencies:
- FastAPI: APIRouter, Depends, HTTPException
- gobby.servers.routes.dependencies: get_internal_manager, get_mcp_manager, get_server
- gobby.utils.metrics: get_metrics_collector
- Helper function: _process_tool_proxy_result (lines 33-105 in tools.py)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Placeholder - handlers will be migrated from tools.py in Phase 3
__all__: list[str] = []
