"""Daemon setup utilities for the install command.

Extracted from install.py to reduce file size. Handles daemon config
creation, database initialization, bundled content sync, MCP server
configuration, and IDE terminal title setup.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from shutil import copy2
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

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
            verb = "Upgraded" if gsqz_result.get("upgraded") else "Installed"
            click.echo(
                f"{verb} gsqz {gsqz_result.get('version', '')} "
                f"via {gsqz_result.get('method', 'unknown')} (output compressor)"
            )
        elif gsqz_result.get("skipped"):
            reason = gsqz_result.get("reason", "")
            suffix = f" ({reason})" if reason else ""
            click.echo(f"gsqz already installed and up to date{suffix}")
        else:
            reason = gsqz_result.get("reason", "unknown error")
            click.echo(f"Warning: Failed to install gsqz: {reason}")
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


# GitHub release URL patterns for gsqz binaries
_GSQZ_RELEASE_URL = "https://github.com/GobbyAI/gsqz/releases/latest/download/gsqz-{target}.tar.gz"
_GSQZ_VERSIONED_RELEASE_URL = (
    "https://github.com/GobbyAI/gsqz/releases/download/v{version}/gsqz-{target}.tar.gz"
)
_GSQZ_CRATES_API = "https://crates.io/api/v1/crates/gsqz"
_GSQZ_VERSION_STAMP = ".gsqz-version"
_GSQZ_BIN_NAME = "gsqz.exe" if sys.platform == "win32" else "gsqz"

# Platform → target triple mapping
_GSQZ_TARGETS: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("win32", "amd64"): "x86_64-pc-windows-msvc",
    ("win32", "arm64"): "aarch64-pc-windows-msvc",
}


def _get_latest_gsqz_version() -> str | None:
    """Query crates.io for the latest gsqz version.

    Returns:
        Version string (e.g. ``"0.1.0"``) or ``None`` on failure.
    """
    try:
        req = Request(_GSQZ_CRATES_API, headers={"User-Agent": "gobby-installer/1.0"})  # noqa: S310
        with urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return data["crate"]["max_version"]
    except (URLError, json.JSONDecodeError, KeyError, OSError) as e:
        logger.debug("gsqz: could not check latest version: %s", e)
        return None


def _get_installed_gsqz_version(bin_dir: Path) -> str | None:
    """Read the installed gsqz version from the stamp file.

    Returns:
        Version string, ``"unknown"`` if binary exists but no stamp, or
        ``None`` if not installed.
    """
    stamp = bin_dir / _GSQZ_VERSION_STAMP
    binary = bin_dir / _GSQZ_BIN_NAME
    if stamp.exists():
        content = stamp.read_text().strip()
        return content if content else None
    if binary.exists():
        return "unknown"
    return None


def _write_gsqz_version_stamp(bin_dir: Path, version: str) -> None:
    """Write version to stamp file atomically."""
    stamp = bin_dir / _GSQZ_VERSION_STAMP
    fd, tmp_path = tempfile.mkstemp(dir=str(bin_dir), prefix=".gsqz-version-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(version + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, stamp)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _install_gsqz_from_github(bin_dir: Path, target: str, version: str | None = None) -> bool:
    """Download and extract gsqz from GitHub Releases.

    Args:
        bin_dir: Target directory (e.g. ``~/.gobby/bin``).
        target: Platform target triple (e.g. ``aarch64-apple-darwin``).
        version: Specific version to download, or ``None`` for latest.

    Returns:
        ``True`` on success, ``False`` on any failure.
    """
    try:
        if version:
            url = _GSQZ_VERSIONED_RELEASE_URL.format(version=version, target=target)
        else:
            url = _GSQZ_RELEASE_URL.format(target=target)
        logger.info("Downloading gsqz from %s", url)
        with urlopen(url, timeout=30) as resp:  # noqa: S310
            tarball = BytesIO(resp.read())

        bin_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=tarball, mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(f"/{_GSQZ_BIN_NAME}") or member.name == _GSQZ_BIN_NAME:
                    member.name = _GSQZ_BIN_NAME
                    tar.extract(member, path=bin_dir)
                    return True
            logger.warning("gsqz binary not found in release tarball")
            return False
    except (URLError, OSError, tarfile.TarError) as e:
        logger.warning("gsqz: GitHub download failed: %s", e)
        return False


def _install_gsqz_from_cargo_binstall(bin_dir: Path, version: str | None = None) -> bool:
    """Install gsqz via cargo-binstall (pre-built binary download).

    Returns:
        ``True`` on success, ``False`` if cargo-binstall is unavailable or fails.
    """
    if not shutil.which("cargo-binstall"):
        return False
    try:
        crate = f"gsqz@{version}" if version else "gsqz"
        result = subprocess.run(
            [
                "cargo-binstall",
                crate,
                "--install-path",
                str(bin_dir),
                "--no-confirm",
                "--no-symlinks",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("gsqz: cargo-binstall failed: %s", e)
        return False


def _install_gsqz_from_cargo_install(bin_dir: Path, version: str | None = None) -> bool:
    """Compile and install gsqz from source via ``cargo install``.

    This is the slowest fallback — compilation can take 30-60 seconds.

    Returns:
        ``True`` on success, ``False`` if cargo is unavailable or fails.
    """
    if not shutil.which("cargo"):
        return False
    try:
        cmd = ["cargo", "install", "gsqz", "--root", str(bin_dir.parent)]
        if version:
            cmd.extend(["--version", version])
        click.echo("  Compiling gsqz from source (this may take 30-60 seconds)...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("gsqz: cargo install failed: %s", e)
        return False


def _ensure_gobby_bin_on_path() -> dict[str, Any]:
    """Add ``~/.gobby/bin`` to the user's shell PATH if not already present.

    Detects the current shell and appends an export line to the appropriate
    rc file with a ``# gobby`` guard comment to avoid duplicates.

    Returns:
        Dict with 'added' (bool), 'shell' (str), and 'rc_file' (str) keys.
    """
    gobby_bin = str(Path.home() / ".gobby" / "bin")
    result: dict[str, Any] = {"added": False}

    # Already on PATH?
    if gobby_bin in os.environ.get("PATH", "").split(os.pathsep):
        return result

    if sys.platform == "win32":
        click.echo(f"  Add {gobby_bin} to your PATH manually (System > Environment Variables)")
        return result

    shell = os.environ.get("SHELL", "")
    shell_name = Path(shell).name if shell else ""

    rc_configs: dict[str, tuple[Path, str]] = {
        "zsh": (Path.home() / ".zshrc", 'export PATH="$HOME/.gobby/bin:$PATH"  # gobby\n'),
        "bash": (Path.home() / ".bashrc", 'export PATH="$HOME/.gobby/bin:$PATH"  # gobby\n'),
        "fish": (
            Path.home() / ".config" / "fish" / "config.fish",
            "fish_add_path ~/.gobby/bin  # gobby\n",
        ),
    }

    if shell_name not in rc_configs:
        logger.debug("gsqz: unknown shell %s, skipping PATH setup", shell_name)
        return result

    rc_file, export_line = rc_configs[shell_name]

    # Check guard: don't append if already present
    if rc_file.exists():
        content = rc_file.read_text()
        if "# gobby" in content and ".gobby/bin" in content:
            return result

    # Ensure parent dir exists (for fish)
    rc_file.parent.mkdir(parents=True, exist_ok=True)

    with open(rc_file, "a") as f:
        f.write(f"\n{export_line}")

    result["added"] = True
    result["shell"] = shell_name
    result["rc_file"] = str(rc_file)
    return result


def _install_gsqz(force: bool = False) -> dict[str, Any]:
    """Install or upgrade the gsqz binary with a fallback chain.

    Installation priority:
      1. GitHub release download (fast, no deps)
      2. ``cargo-binstall`` (fast if available)
      3. ``cargo install`` (compiles from source)

    Args:
        force: Re-download even if the installed version is current.

    Returns:
        Dict with keys: ``installed``, ``skipped``, ``upgraded``,
        ``version``, ``method``, ``reason``.
    """
    bin_dir = Path.home() / ".gobby" / "bin"
    gsqz_path = bin_dir / _GSQZ_BIN_NAME

    # Detect platform
    os_name = sys.platform
    machine = platform.machine().lower()
    target = _GSQZ_TARGETS.get((os_name, machine))
    if target is None:
        logger.warning("gsqz: unsupported platform %s/%s", os_name, machine)
        return {
            "installed": False,
            "skipped": True,
            "reason": f"unsupported platform {os_name}/{machine}",
        }

    # Version check
    installed_version = _get_installed_gsqz_version(bin_dir)
    latest_version = _get_latest_gsqz_version()

    if gsqz_path.exists() and not force:
        if installed_version and latest_version and installed_version == latest_version:
            return {"installed": False, "skipped": True, "version": installed_version}
        if installed_version and installed_version != "unknown" and latest_version is None:
            return {
                "installed": False,
                "skipped": True,
                "version": installed_version,
                "reason": "version check failed, keeping current",
            }

    # Fallback chain
    target_version = latest_version
    bin_dir.mkdir(parents=True, exist_ok=True)
    method = None

    if _install_gsqz_from_github(bin_dir, target, target_version):
        method = "github"
    elif _install_gsqz_from_cargo_binstall(bin_dir, target_version):
        method = "cargo-binstall"
    elif _install_gsqz_from_cargo_install(bin_dir, target_version):
        method = "cargo-install"
    else:
        return {"installed": False, "skipped": False, "reason": "all installation methods failed"}

    gsqz_path.chmod(0o755)
    resolved_version = target_version or "latest"
    _write_gsqz_version_stamp(bin_dir, resolved_version)

    # Ensure ~/.gobby/bin is on PATH
    path_result = _ensure_gobby_bin_on_path()
    if path_result.get("added"):
        click.echo(
            f"  Added ~/.gobby/bin to PATH in {path_result['rc_file']} (restart shell or source it)"
        )

    is_upgrade = installed_version is not None and installed_version != resolved_version
    return {
        "installed": True,
        "upgraded": is_upgrade,
        "version": resolved_version,
        "method": method,
    }
