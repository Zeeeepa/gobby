"""
Registry endpoints for MCP tool search and recommendations.

Target endpoints to migrate from tools.py:
- POST /tools/recommend (line 852) - recommend_tools
- POST /tools/search (line 933) - search_tools
- POST /tools/embed (line 1035) - embed_tools

Importer analysis:
- These are nested route handlers inside create_mcp_router()
- No external modules import these handlers directly
- Migration: Extract as standalone async functions, register in router factory

Dependencies:
- FastAPI: APIRouter, Depends, HTTPException
- gobby.servers.routes.dependencies: get_server
- gobby.utils.metrics: get_metrics_collector
- gobby.mcp_proxy.tool_recommender (for recommend_tools)
- gobby.mcp_proxy.tool_search (for search_tools, embed_tools)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Placeholder - handlers will be migrated from tools.py in Phase 3
__all__: list[str] = []
