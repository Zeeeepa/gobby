"""
Antigravity agent installation for Gobby MCP.

This module handles installing Gobby MCP server configuration
for the Antigravity agent (internal tool).

Note: Antigravity does not currently support hooks, so only MCP
configuration is installed.
"""

import logging
from pathlib import Path
from typing import Any

from .shared import configure_mcp_server_json

logger = logging.getLogger(__name__)


def install_antigravity(project_path: Path) -> dict[str, Any]:
    """Install Gobby integration for Antigravity agent (MCP only).

    Antigravity does not support hooks, so this only configures
    the MCP server in ~/.gemini/antigravity/mcp_config.json.

    Args:
        project_path: Path to the project root (unused, kept for API compatibility)

    Returns:
        Dict with installation results including success status
    """
    result: dict[str, Any] = {
        "success": False,
        "hooks_installed": [],
        "workflows_installed": [],
        "commands_installed": [],
        "skills_installed": [],
        "mcp_configured": False,
        "mcp_already_configured": False,
        "error": None,
    }

    # Configure MCP server in Antigravity's MCP config (~/.gemini/antigravity/mcp_config.json)
    mcp_config = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"

    # Skills are now auto-synced to database on daemon startup (sync_bundled_skills)
    # No longer need to copy to .antigravity/skills/

    mcp_result = configure_mcp_server_json(mcp_config)

    if mcp_result["success"]:
        result["mcp_configured"] = mcp_result.get("added", False)
        result["mcp_already_configured"] = mcp_result.get("already_configured", False)
        result["success"] = True
    else:
        result["error"] = mcp_result.get("error", "Unknown error configuring MCP")
        logger.error(f"Failed to configure MCP server: {result['error']}")

    return result
