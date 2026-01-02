"""MCP tool invocation workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle MCP tool calls from workflows.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def call_mcp_tool(
    mcp_manager: Any,
    state: Any,
    server_name: str | None,
    tool_name: str | None,
    arguments: dict[str, Any] | None = None,
    output_as: str | None = None,
) -> dict[str, Any]:
    """Call an MCP tool on a connected server.

    Args:
        mcp_manager: MCP client manager instance
        state: WorkflowState object for storing results
        server_name: Name of the MCP server
        tool_name: Name of the tool to call
        arguments: Arguments to pass to the tool
        output_as: Optional variable name to store result

    Returns:
        Dict with result and stored_as, or error
    """
    if not server_name or not tool_name:
        return {"error": "Missing server_name or tool_name"}

    if not mcp_manager:
        logger.warning("call_mcp_tool: MCP manager not available")
        return {"error": "MCP manager not available"}

    try:
        # Check connection
        if server_name not in mcp_manager.connections:
            return {"error": f"Server {server_name} not connected"}

        # Call tool
        result = await mcp_manager.call_tool(
            server_name, tool_name, arguments or {}
        )

        # Store result in workflow variable if 'as' specified
        if output_as:
            if not state.variables:
                state.variables = {}
            state.variables[output_as] = result

        return {"result": result, "stored_as": output_as}
    except Exception as e:
        logger.error(f"call_mcp_tool: Failed: {e}")
        return {"error": str(e)}
