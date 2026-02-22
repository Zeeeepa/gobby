"""Daemon setup utilities for the install command.

Extracted from install.py to reduce file size. Handles daemon config
creation, database initialization, bundled content sync, MCP server
configuration, and IDE terminal title setup.
"""

from __future__ import annotations

import logging
from pathlib import Path
from shutil import copy2
from typing import Any

import click

from .utils import get_install_dir

logger = logging.getLogger(__name__)


def ensure_daemon_config() -> dict[str, Any]:
    """Ensure bootstrap config exists at ~/.gobby/bootstrap.yaml.

    If bootstrap.yaml doesn't exist, copies the shared template.
    Bootstrap.yaml contains only the 5 pre-DB settings; all other
    configuration is managed via the DB (config_store) + Pydantic defaults.

    Returns:
        Dict with 'created' (bool) and 'path' (str) keys
    """
    bootstrap_path = Path("~/.gobby/bootstrap.yaml").expanduser()

    if bootstrap_path.exists():
        return {"created": False, "path": str(bootstrap_path)}

    # Ensure directory exists
    bootstrap_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy shared bootstrap template
    shared_bootstrap = get_install_dir() / "shared" / "config" / "bootstrap.yaml"
    if shared_bootstrap.exists():
        copy2(shared_bootstrap, bootstrap_path)
        bootstrap_path.chmod(0o600)
        return {"created": True, "path": str(bootstrap_path), "source": "shared"}

    # Fallback: write minimal defaults directly
    import yaml

    defaults = {
        "database_path": "~/.gobby/gobby-hub.db",
        "daemon_port": 60887,
        "bind_host": "localhost",
        "websocket_port": 60888,
        "ui_port": 60889,
    }
    with open(bootstrap_path, "w") as f:
        yaml.safe_dump(defaults, f, default_flow_style=False, sort_keys=False)
    bootstrap_path.chmod(0o600)
    return {"created": True, "path": str(bootstrap_path), "source": "generated"}


def run_daemon_setup(project_path: Path) -> None:
    """Run install setup: DB init, bundled content sync, MCP servers, IDE config.

    Called after ensure_daemon_config(). Handles database initialization,
    bundled content sync, default MCP server installation, and IDE config.

    Args:
        project_path: The project directory path (used for context only).
    """
    from .installers import install_default_mcp_servers

    # Initialize database (ensures _personal project exists before daemon start)
    db = None
    try:
        from gobby.cli.utils import init_local_storage

        db = init_local_storage()
        click.echo("Database initialized")
    except (OSError, PermissionError, ValueError) as e:
        click.echo(f"Warning: Database init failed ({type(e).__name__}): {e}")

    # Sync bundled content (skills, prompts, rules, agents) to database.
    # This is the single import point — the daemon no longer syncs on startup.
    if db is not None:
        try:
            from gobby.cli.installers.shared import sync_bundled_content_to_db

            sync_result = sync_bundled_content_to_db(db)
            if sync_result["total_synced"] > 0:
                click.echo(f"Synced {sync_result['total_synced']} bundled items to database")
            if sync_result["errors"]:
                for err in sync_result["errors"]:
                    click.echo(f"  Warning: {err}")
        finally:
            db.close()

    # Install default external MCP servers (GitHub, Linear, context7)
    mcp_result = install_default_mcp_servers()
    if mcp_result["success"]:
        if mcp_result["servers_added"]:
            click.echo(f"Added MCP servers to proxy: {', '.join(mcp_result['servers_added'])}")
        if mcp_result["servers_skipped"]:
            click.echo(
                f"MCP servers already configured: {', '.join(mcp_result['servers_skipped'])}"
            )
    else:
        click.echo(f"Warning: Failed to configure MCP servers: {mcp_result['error']}")

    # Configure VS Code terminal title (any CLI may run inside VS Code's terminal)
    try:
        from .installers.ide_config import configure_ide_terminal_title

        vscode_result = configure_ide_terminal_title("Code")
        if vscode_result.get("added"):
            click.echo("Configured VS Code terminal title for tmux integration")
    except (ImportError, OSError, PermissionError, ValueError) as e:
        click.echo(f"Warning: Failed to configure VS Code terminal title: {e}")
