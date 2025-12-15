"""
Tool Filesystem Manager for lazy loading MCP tool schemas.

Manages the ~/.gobby/tools/ directory structure that enables progressive
disclosure of MCP tool schemas. Tool metadata is stored in .mcp.json for
quick listing, while full schemas are stored in individual JSON files for
on-demand loading.

Directory structure:
    ~/.gobby/
    ├── .mcp.json                 # Lightweight metadata
    └── tools/                    # Full tool schemas
        ├── context7/
        │   ├── get-library-docs.json
        │   └── resolve-library-id.json
        └── supabase/
            ├── list_tables.json
            └── run_query.json
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_tools_dir() -> Path:
    """
    Get path to tools directory.

    Returns:
        Path to ~/.gobby/tools/
    """
    return Path("~/.gobby/tools").expanduser()


def generate_brief(description: str | None, max_length: int = 100) -> str:
    """
    Generate brief description from full description.

    Extracts first sentence or truncates to max_length.

    Args:
        description: Full tool description
        max_length: Maximum length for brief description

    Returns:
        Brief description string
    """
    if not description:
        return "No description available"

    # Try to extract first sentence
    for delimiter in [".", "!", "?"]:
        if delimiter in description:
            first_sentence = description.split(delimiter)[0] + delimiter
            if len(first_sentence) <= max_length:
                return first_sentence.strip()

    # Fallback: truncate to max_length
    if len(description) <= max_length:
        return description.strip()

    return description[:max_length].strip() + "..."


def write_tool_schema(server_name: str, tool_name: str, tool_data: dict[str, Any]) -> None:
    """
    Write tool schema to filesystem.

    Creates server directory if needed and writes tool schema as JSON file.

    Args:
        server_name: Name of the MCP server
        tool_name: Name of the tool
        tool_data: Tool schema data (name, description, inputSchema)

    Raises:
        OSError: If file operations fail
    """
    # Create server directory
    server_dir = get_tools_dir() / server_name
    server_dir.mkdir(parents=True, exist_ok=True)

    # Write tool schema
    tool_file = server_dir / f"{tool_name}.json"
    with open(tool_file, "w") as f:
        json.dump(tool_data, f, indent=2)

    logger.debug(f"Wrote tool schema: {server_name}/{tool_name}")


def write_server_tools(
    server_name: str, tools: list[dict[str, Any]], tools_dir: Path | None = None
) -> int:
    """
    Write all tool schemas for a server to filesystem.

    Args:
        server_name: Name of the MCP server
        tools: List of tool dicts with name, description, args (inputSchema)
        tools_dir: Optional custom directory to write tools to (default: ~/.gobby/tools/)

    Returns:
        Number of tools written

    Raises:
        OSError: If file operations fail
    """
    # Create server directory
    base_dir = tools_dir if tools_dir else get_tools_dir()
    server_dir = base_dir / server_name
    server_dir.mkdir(parents=True, exist_ok=True)

    # Write each tool
    for tool in tools:
        tool_name = tool.get("name")
        if not tool_name:
            logger.warning(f"Skipping tool without name in server '{server_name}'")
            continue

        # Handle None values properly - description should be string, args should be dict
        description = tool.get("description")
        args = tool.get("args")

        tool_data = {
            "name": tool_name,
            "description": description if description else "",
            "inputSchema": args if args else {},  # 'args' in our schema = 'inputSchema' in MCP
        }

        tool_file = server_dir / f"{tool_name}.json"
        with open(tool_file, "w") as f:
            json.dump(tool_data, f, indent=2)

    logger.info(f"Wrote {len(tools)} tool schemas for server '{server_name}'")
    return len(tools)


def read_tool_schema(
    server_name: str, tool_name: str, tools_dir: Path | None = None
) -> dict[str, Any] | None:
    """
    Read tool schema from filesystem.

    Args:
        server_name: Name of the MCP server
        tool_name: Name of the tool
        tools_dir: Optional custom directory to read tools from

    Returns:
        Tool schema dict, or None if not found

    Raises:
        ValueError: If JSON is invalid
        OSError: If file read fails
    """
    base_dir = tools_dir if tools_dir else get_tools_dir()
    tool_file = base_dir / server_name / f"{tool_name}.json"

    if not tool_file.exists():
        return None

    with open(tool_file) as f:
        return json.load(f)


def remove_server_tools(server_name: str, tools_dir: Path | None = None) -> None:
    """
    Remove all tool schemas for a server from filesystem.

    Deletes the entire server directory.

    Args:
        server_name: Name of the MCP server to remove
        tools_dir: Optional custom directory to remove tools from

    Raises:
        OSError: If directory removal fails
    """
    base_dir = tools_dir if tools_dir else get_tools_dir()
    server_dir = base_dir / server_name

    if server_dir.exists():
        shutil.rmtree(server_dir)
        logger.info(f"Removed tool directory for server '{server_name}'")
    else:
        logger.debug(f"Tool directory for '{server_name}' does not exist (OK)")


def cleanup_removed_tools(
    server_name: str, current_tool_names: list[str], tools_dir: Path | None = None
) -> int:
    """
    Remove tool files that no longer exist on the server.

    Compares filesystem tools with current tool list and removes orphans.

    Args:
        server_name: Name of the MCP server
        current_tool_names: List of tool names that currently exist
        tools_dir: Optional custom directory to cleanup tools in

    Returns:
        Number of orphaned tools removed

    Raises:
        OSError: If file operations fail
    """
    base_dir = tools_dir if tools_dir else get_tools_dir()
    server_dir = base_dir / server_name

    if not server_dir.exists():
        return 0

    # Get existing tool files
    existing_files = list(server_dir.glob("*.json"))
    current_tool_files = {f"{name}.json" for name in current_tool_names}

    # Remove orphaned tools
    removed_count = 0
    for tool_file in existing_files:
        if tool_file.name not in current_tool_files:
            tool_file.unlink()
            logger.debug(f"Removed orphaned tool file: {server_name}/{tool_file.name}")
            removed_count += 1

    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} orphaned tools for server '{server_name}'")

    return removed_count


def list_server_tools(server_name: str, tools_dir: Path | None = None) -> list[str]:
    """
    List all tool names for a server from filesystem.

    Args:
        server_name: Name of the MCP server
        tools_dir: Optional custom directory to list tools from

    Returns:
        List of tool names (without .json extension)
    """
    base_dir = tools_dir if tools_dir else get_tools_dir()
    server_dir = base_dir / server_name

    if not server_dir.exists():
        return []

    return [f.stem for f in server_dir.glob("*.json")]
