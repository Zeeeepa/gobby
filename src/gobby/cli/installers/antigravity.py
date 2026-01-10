"""
Antigravity agent installation for Gobby hooks.

This module handles installing Gobby hooks and workflows
for the Antigravity agent (internal tool).
"""

import json
import logging
import time
from pathlib import Path
from shutil import copy2, which
from typing import Any

from gobby.cli.utils import get_install_dir

from .shared import (
    configure_mcp_server_json,
    install_cli_content,
    install_shared_content,
)

logger = logging.getLogger(__name__)


def install_antigravity(project_path: Path) -> dict[str, Any]:
    """Install Gobby integration for Antigravity agent (hooks, workflows).

    Args:
        project_path: Path to the project root

    Returns:
        Dict with installation results including success status and installed items
    """
    hooks_installed: list[str] = []
    result: dict[str, Any] = {
        "success": False,
        "hooks_installed": hooks_installed,
        "workflows_installed": [],
        "commands_installed": [],
        "mcp_configured": False,
        "mcp_already_configured": False,
        "error": None,
    }

    antigravity_path = project_path / ".antigravity"
    settings_file = antigravity_path / "settings.json"

    # Ensure .antigravity subdirectories exist
    antigravity_path.mkdir(parents=True, exist_ok=True)
    hooks_dir = antigravity_path / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Get source files
    install_dir = get_install_dir()
    antigravity_install_dir = install_dir / "antigravity"
    install_hooks_dir = antigravity_install_dir / "hooks"
    source_hooks_template = antigravity_install_dir / "hooks-template.json"

    # Verify source files exist
    dispatcher_file = install_hooks_dir / "hook_dispatcher.py"
    if not dispatcher_file.exists():
        result["error"] = f"Missing hook dispatcher: {dispatcher_file}"
        return result

    if not source_hooks_template.exists():
        result["error"] = f"Missing hooks template: {source_hooks_template}"
        return result

    # Copy hook dispatcher
    target_dispatcher = hooks_dir / "hook_dispatcher.py"
    if target_dispatcher.exists():
        target_dispatcher.unlink()
    copy2(dispatcher_file, target_dispatcher)
    target_dispatcher.chmod(0o755)

    # Install shared content (workflows)
    shared = install_shared_content(antigravity_path, project_path)
    # Install CLI-specific content (can override shared)
    cli = install_cli_content("antigravity", antigravity_path)

    result["workflows_installed"] = shared["workflows"] + cli["workflows"]
    result["commands_installed"] = cli.get("commands", [])
    result["plugins_installed"] = shared.get("plugins", [])

    # Backup existing settings.json if it exists
    if settings_file.exists():
        timestamp = int(time.time())
        backup_file = antigravity_path / f"settings.json.{timestamp}.backup"
        copy2(settings_file, backup_file)

    # Load existing settings or create empty
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                existing_settings = json.load(f)
        except json.JSONDecodeError:
            existing_settings = {}
    else:
        existing_settings = {}

    # Load Gobby hooks from template
    with open(source_hooks_template) as f:
        gobby_settings_str = f.read()

    # Resolve uv path
    uv_path = which("uv")
    if not uv_path:
        uv_path = "uv"

    abs_project_path = str(project_path.resolve())

    # Replace variables
    gobby_settings_str = gobby_settings_str.replace("$PROJECT_PATH", abs_project_path)
    if uv_path != "uv":
        gobby_settings_str = gobby_settings_str.replace("uv run python", f"{uv_path} run python")

    gobby_settings = json.loads(gobby_settings_str)

    # Ensure hooks section exists
    if "hooks" not in existing_settings:
        existing_settings["hooks"] = {}

    # Merge Gobby hooks
    gobby_hooks = gobby_settings.get("hooks", {})
    for hook_type, hook_config in gobby_hooks.items():
        existing_settings["hooks"][hook_type] = hook_config
        hooks_installed.append(hook_type)

    # Enable hooks
    if "general" not in existing_settings:
        existing_settings["general"] = {}
    existing_settings["general"]["enableHooks"] = True

    # Write settings
    with open(settings_file, "w") as f:
        json.dump(existing_settings, f, indent=2)

    # Configure MCP server in Antigravity's MCP config (~/.gemini/antigravity/mcp_config.json)
    mcp_config = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    mcp_result = configure_mcp_server_json(mcp_config)
    if mcp_result["success"]:
        result["mcp_configured"] = mcp_result.get("added", False)
        result["mcp_already_configured"] = mcp_result.get("already_configured", False)
    else:
        # MCP config failure is non-fatal, just log it
        logger.warning(f"Failed to configure MCP server: {mcp_result['error']}")

    result["success"] = True
    return result
