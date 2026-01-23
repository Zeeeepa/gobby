"""
Codex CLI installation for Gobby hooks.

This module handles installing and uninstalling Gobby notify integration
for OpenAI Codex CLI.
"""

import json
import logging
import re
from pathlib import Path
from shutil import copy2
from typing import Any

from gobby.cli.utils import get_install_dir

from .shared import (
    configure_mcp_server_toml,
    install_cli_content,
    install_shared_content,
    remove_mcp_server_toml,
)

logger = logging.getLogger(__name__)


def install_codex_notify() -> dict[str, Any]:
    """Install Codex notify script and configure ~/.codex/config.toml.

    Returns:
        Dict with installation results including success status and installed items
    """
    files_installed: list[str] = []
    result: dict[str, Any] = {
        "success": False,
        "files_installed": files_installed,
        "workflows_installed": [],
        "commands_installed": [],
        "config_updated": False,
        "mcp_configured": False,
        "mcp_already_configured": False,
        "error": None,
    }

    install_dir = get_install_dir()
    source_notify = install_dir / "codex" / "hooks" / "hook_dispatcher.py"
    if not source_notify.exists():
        result["error"] = f"Missing source file: {source_notify}"
        return result

    # Install hook dispatcher to ~/.gobby/hooks/codex/hook_dispatcher.py
    notify_dir = Path.home() / ".gobby" / "hooks" / "codex"
    notify_dir.mkdir(parents=True, exist_ok=True)
    target_notify = notify_dir / "hook_dispatcher.py"

    if target_notify.exists():
        target_notify.unlink()

    copy2(source_notify, target_notify)
    target_notify.chmod(0o755)
    files_installed.append(str(target_notify))

    # Install shared content - workflows to ~/.gobby
    codex_home = Path.home() / ".codex"
    gobby_home = Path.home()  # workflows go to ~/.gobby/workflows/

    shared = install_shared_content(codex_home, gobby_home)
    # Install CLI-specific content (can override shared)
    cli = install_cli_content("codex", codex_home)

    # Skills are now auto-synced to database on daemon startup (sync_bundled_skills)
    # No longer need to copy to .codex/skills/

    result["workflows_installed"] = shared["workflows"] + cli["workflows"]
    result["commands_installed"] = cli.get("commands", [])
    result["plugins_installed"] = shared.get("plugins", [])

    # Update ~/.codex/config.toml
    codex_config_dir = codex_home

    codex_config_dir.mkdir(parents=True, exist_ok=True)
    codex_config_path = codex_config_dir / "config.toml"

    notify_command = ["python3", str(target_notify)]
    notify_line = f"notify = {json.dumps(notify_command)}"

    try:
        if codex_config_path.exists():
            existing = codex_config_path.read_text(encoding="utf-8")
        else:
            existing = ""

        pattern = re.compile(r"(?m)^\s*notify\s*=.*$")
        if pattern.search(existing):
            updated = pattern.sub(notify_line, existing)
        else:
            updated = (existing.rstrip() + "\n\n" if existing.strip() else "") + notify_line + "\n"

        if updated != existing:
            if codex_config_path.exists():
                backup_path = codex_config_path.with_suffix(".toml.bak")
                backup_path.write_text(existing, encoding="utf-8")

            codex_config_path.write_text(updated, encoding="utf-8")
            result["config_updated"] = True

        # Configure MCP server in global config (~/.codex/config.toml)
        mcp_result = configure_mcp_server_toml(codex_config_path)
        if mcp_result["success"]:
            result["mcp_configured"] = mcp_result.get("added", False)
            result["mcp_already_configured"] = mcp_result.get("already_configured", False)
        else:
            # MCP config failure is non-fatal, just log it
            logger.warning(f"Failed to configure MCP server: {mcp_result['error']}")

        result["success"] = True
        return result

    except Exception as e:
        result["error"] = f"Failed to update Codex config: {e}"
        return result


def uninstall_codex_notify() -> dict[str, Any]:
    """Uninstall Codex notify script and remove from ~/.codex/config.toml.

    Returns:
        Dict with uninstallation results including success status and removed items
    """
    files_removed: list[str] = []
    result: dict[str, Any] = {
        "success": False,
        "files_removed": files_removed,
        "config_updated": False,
        "mcp_removed": False,
        "error": None,
    }

    # Remove hook dispatcher from ~/.gobby/hooks/codex/hook_dispatcher.py
    notify_file = Path.home() / ".gobby" / "hooks" / "codex" / "hook_dispatcher.py"
    if notify_file.exists():
        notify_file.unlink()
        files_removed.append(str(notify_file))

    # Try to remove empty parent directories
    notify_dir = notify_file.parent
    try:
        if notify_dir.exists() and not any(notify_dir.iterdir()):
            notify_dir.rmdir()
    except Exception:
        pass  # nosec B110 - best-effort cleanup, directory removal is non-critical

    # Update ~/.codex/config.toml to remove notify line
    codex_config_path = Path.home() / ".codex" / "config.toml"

    try:
        if codex_config_path.exists():
            existing = codex_config_path.read_text(encoding="utf-8")

            # Remove notify = [...] line
            pattern = re.compile(r"(?m)^\s*notify\s*=.*$\n?")
            if pattern.search(existing):
                updated = pattern.sub("", existing)

                # Clean up multiple blank lines
                updated = re.sub(r"\n{3,}", "\n\n", updated)

                if updated != existing:
                    # Backup before modifying
                    backup_path = codex_config_path.with_suffix(".toml.bak")
                    backup_path.write_text(existing, encoding="utf-8")

                    codex_config_path.write_text(updated, encoding="utf-8")
                    result["config_updated"] = True

        # Remove MCP server from config
        mcp_result = remove_mcp_server_toml(codex_config_path)
        if mcp_result["success"]:
            result["mcp_removed"] = mcp_result.get("removed", False)

        result["success"] = True
        return result

    except Exception as e:
        result["error"] = f"Failed to update Codex config: {e}"
        return result
