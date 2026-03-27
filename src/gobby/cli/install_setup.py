"""Daemon setup utilities for the install command.

Extracted from install.py to reduce file size. Handles daemon config
creation, database initialization, bundled content sync, MCP server
configuration, and IDE terminal title setup.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from shutil import copy2
from typing import Any
from urllib.request import urlopen

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

    # Install Playwright CLI globally (token-efficient browser automation)
    try:
        npm_result = subprocess.run(
            ["npm", "install", "-g", "@playwright/cli@latest"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if npm_result.returncode == 0:
            click.echo("Installed Playwright CLI (@playwright/cli)")
            # Install skills so coding agents auto-discover commands
            skills_result = subprocess.run(
                ["playwright-cli", "install", "--skills"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if skills_result.returncode != 0:
                click.echo(
                    f"Warning: Playwright skills install failed: {skills_result.stderr.strip()}"
                )
        else:
            click.echo(f"Warning: Failed to install Playwright CLI: {npm_result.stderr.strip()}")
    except FileNotFoundError:
        click.echo("Warning: npm not found — skipping Playwright CLI install")
    except subprocess.TimeoutExpired:
        click.echo("Warning: Playwright CLI install timed out")

    # Install ClawHub CLI (skill hub search)
    try:
        npm_result = subprocess.run(
            ["npm", "install", "-g", "clawhub"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if npm_result.returncode == 0:
            click.echo("Installed ClawHub CLI (clawhub)")
        else:
            click.echo(f"Warning: Failed to install ClawHub CLI: {npm_result.stderr.strip()}")
    except FileNotFoundError:
        click.echo("Warning: npm not found — skipping ClawHub CLI install")
    except subprocess.TimeoutExpired:
        click.echo("Warning: ClawHub CLI install timed out")

    # Install gsqz binary (output compressor for token optimization)
    try:
        gsqz_result = _install_gsqz()
        if gsqz_result.get("installed"):
            click.echo(f"Installed gsqz {gsqz_result.get('version', '')} (output compressor)")
        elif gsqz_result.get("skipped"):
            click.echo("gsqz already installed, skipping")
    except Exception as e:
        click.echo(f"Warning: Failed to install gsqz: {e}")

    # Configure VS Code terminal title (any CLI may run inside VS Code's terminal)
    try:
        from .installers.ide_config import configure_ide_terminal_title

        vscode_result = configure_ide_terminal_title("Code")
        if vscode_result.get("added"):
            click.echo("Configured VS Code terminal title for tmux integration")
    except (ImportError, OSError, PermissionError, ValueError) as e:
        click.echo(f"Warning: Failed to configure VS Code terminal title: {e}")


# GitHub release URL pattern for gsqz binaries
_GSQZ_RELEASE_URL = "https://github.com/GobbyAI/gsqz/releases/latest/download/gsqz-{target}.tar.gz"

# Platform → target triple mapping
_GSQZ_TARGETS: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
}


def _install_gsqz() -> dict[str, Any]:
    """Download and install the gsqz binary from GitHub Releases.

    Installs to ~/.gobby/bin/gsqz. Skips if already present.

    Returns:
        Dict with 'installed', 'skipped', and optionally 'version' keys.
    """
    bin_dir = Path.home() / ".gobby" / "bin"
    gsqz_path = bin_dir / "gsqz"

    if gsqz_path.exists():
        return {"installed": False, "skipped": True}

    # Detect platform
    os_name = sys.platform  # 'darwin' or 'linux'
    machine = platform.machine().lower()  # 'arm64', 'x86_64', 'aarch64'
    target = _GSQZ_TARGETS.get((os_name, machine))
    if target is None:
        logger.warning("gsqz: unsupported platform %s/%s", os_name, machine)
        return {
            "installed": False,
            "skipped": True,
            "reason": f"unsupported platform {os_name}/{machine}",
        }

    # Download tarball
    url = _GSQZ_RELEASE_URL.format(target=target)
    logger.info("Downloading gsqz from %s", url)
    with urlopen(url, timeout=30) as resp:  # noqa: S310
        tarball = BytesIO(resp.read())

    # Extract gsqz binary
    bin_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=tarball, mode="r:gz") as tar:
        # Find the gsqz binary in the archive
        for member in tar.getmembers():
            if member.name.endswith("/gsqz") or member.name == "gsqz":
                member.name = "gsqz"  # Flatten path
                tar.extract(member, path=bin_dir)
                break
        else:
            raise FileNotFoundError("gsqz binary not found in release tarball")

    gsqz_path.chmod(0o755)
    return {"installed": True, "version": "latest"}
