"""
CLI commands for Gobby web UI management and development.
"""

import os
import subprocess  # nosec B404 - subprocess needed for npm commands
import sys
from pathlib import Path

import click

from .utils import find_web_dir, get_gobby_home, spawn_ui_server, stop_ui_server

# Path to web UI directory (legacy fallback)
WEB_UI_DIR = Path(__file__).parent.parent / "ui" / "web"


def _get_ui_pid() -> int | None:
    """Read UI server PID if running."""
    pid_file = get_gobby_home() / "ui.pid"
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ProcessLookupError, ValueError, OSError):
        return None


def _ensure_npm_deps_installed(web_dir: Path) -> bool:
    """Install npm dependencies if node_modules is missing. Returns True on success."""
    if (web_dir / "node_modules").exists():
        return True
    click.echo("Installing dependencies...")
    try:
        result = subprocess.run(  # nosec B603 B607
            ["npm", "install"],
            cwd=web_dir,
            capture_output=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        click.echo("npm install timed out after 120 seconds", err=True)
        return False
    except FileNotFoundError:
        click.echo("npm not found. Please install Node.js and npm.", err=True)
        return False
    except OSError as e:
        click.echo(f"Failed to run npm install: {e}", err=True)
        return False
    return result.returncode == 0


@click.group()
def ui() -> None:
    """Web UI management and development commands."""
    pass


@ui.command("start")
@click.pass_context
def ui_start(ctx: click.Context) -> None:
    """Start the web UI server."""
    config = ctx.obj["config"]

    if not config.ui.enabled:
        click.echo("Web UI is not enabled. Set ui.enabled: true in config.", err=True)
        sys.exit(1)

    # Check if already running (dev mode)
    if config.ui.mode == "dev":
        existing_pid = _get_ui_pid()
        if existing_pid:
            click.echo(f"UI server is already running (PID: {existing_pid})", err=True)
            sys.exit(1)

        web_dir = find_web_dir(config)
        if not web_dir:
            click.echo("Error: Web UI directory not found", err=True)
            sys.exit(1)

        ui_log = Path(config.logging.client).expanduser().parent / "ui.log"
        pid = spawn_ui_server(config.ui.host, config.ui.port, web_dir, ui_log)
        if pid:
            click.echo(
                f"UI dev server started (PID: {pid}) at http://{config.ui.host}:{config.ui.port}"
            )
        else:
            click.echo("Failed to start UI server", err=True)
            sys.exit(1)
    else:
        click.echo("Production mode UI is served by the daemon automatically.")
        click.echo("Ensure the daemon is running with 'gobby start'.")


@ui.command("stop")
def ui_stop() -> None:
    """Stop the web UI server."""
    pid = _get_ui_pid()
    if not pid:
        click.echo("UI server is not running")
        return

    success = stop_ui_server(quiet=False)
    if success:
        click.echo("UI server stopped")
    else:
        click.echo("Failed to stop UI server", err=True)
        sys.exit(1)


@ui.command("restart")
@click.pass_context
def ui_restart(ctx: click.Context) -> None:
    """Restart the web UI server."""
    stop_ui_server(quiet=True)
    ctx.invoke(ui_start)


@ui.command("status")
@click.pass_context
def ui_status(ctx: click.Context) -> None:
    """Show web UI server status."""
    config = ctx.obj["config"]

    if not config.ui.enabled:
        click.echo("Web UI: Disabled")
        return

    click.echo(f"Web UI: Enabled (mode: {config.ui.mode})")

    if config.ui.mode == "dev":
        pid = _get_ui_pid()
        if pid:
            click.echo(f"  Status: Running (PID: {pid})")
            click.echo(f"  URL: http://{config.ui.host}:{config.ui.port}")
        else:
            click.echo("  Status: Stopped")
    elif config.ui.mode == "production":
        click.echo(f"  URL: http://localhost:{config.daemon_port}/")
        click.echo("  Status: Served by daemon (check 'gobby status')")


@ui.command()
@click.option("--port", "-p", default=60889, help="Dev server port")
@click.option("--host", "-h", default="localhost", help="Dev server host")
def dev(port: int, host: str) -> None:
    """Start the web UI development server with hot-reload (foreground)."""
    if not WEB_UI_DIR.exists():
        click.echo(f"Error: Web UI directory not found at {WEB_UI_DIR}", err=True)
        sys.exit(1)

    package_json = WEB_UI_DIR / "package.json"
    if not package_json.exists():
        click.echo(f"Error: package.json not found at {package_json}", err=True)
        sys.exit(1)

    if not _ensure_npm_deps_installed(WEB_UI_DIR):
        click.echo("Failed to install dependencies", err=True)
        sys.exit(1)

    click.echo(f"Starting dev server at http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")
    click.echo()

    try:
        subprocess.run(  # nosec B603 B607
            ["npm", "run", "dev", "--", "--host", host, "--port", str(port)],
            cwd=WEB_UI_DIR,
            check=True,
        )
    except KeyboardInterrupt:
        click.echo("\nDev server stopped")
    except subprocess.CalledProcessError as e:
        click.echo(f"Dev server failed with code {e.returncode}", err=True)
        sys.exit(e.returncode)


@ui.command()
def build() -> None:
    """Build the web UI for production."""
    if not WEB_UI_DIR.exists():
        click.echo(f"Error: Web UI directory not found at {WEB_UI_DIR}", err=True)
        sys.exit(1)

    if not _ensure_npm_deps_installed(WEB_UI_DIR):
        click.echo("Failed to install dependencies", err=True)
        sys.exit(1)

    click.echo("Building web UI...")
    result = subprocess.run(  # nosec B603 B607
        ["npm", "run", "build"],
        cwd=WEB_UI_DIR,
        capture_output=False,
    )

    if result.returncode == 0:
        dist_dir = WEB_UI_DIR / "dist"
        click.echo(f"Build complete: {dist_dir}")
    else:
        click.echo("Build failed", err=True)
        sys.exit(result.returncode)


@ui.command()
def install_deps() -> None:
    """Install web UI dependencies."""
    if not WEB_UI_DIR.exists():
        click.echo(f"Error: Web UI directory not found at {WEB_UI_DIR}", err=True)
        sys.exit(1)

    if _ensure_npm_deps_installed(WEB_UI_DIR):
        click.echo("Dependencies installed")
    else:
        click.echo("Failed to install dependencies", err=True)
        sys.exit(1)
