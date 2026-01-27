"""
MCP endpoint modules for the Gobby HTTP server.

This package contains decomposed endpoint handlers extracted from tools.py
using the Strangler Fig pattern. Each module handles a specific domain:

- discovery: Tool and server listing endpoints
- execution: Tool invocation endpoints
- server: Server management (add/remove/import)
- registry: Tool search, recommendations, and embeddings

Importer analysis:
- Only src/gobby/servers/routes/mcp/__init__.py imports from tools.py
- Import: `from gobby.servers.routes.mcp.tools import create_mcp_router`
- No test files directly import from tools.py
"""

# Phase 2: Placeholders - exports will be added as handlers are migrated
__all__: list[str] = []
