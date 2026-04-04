"""
Daemon management commands.
"""

import asyncio
import contextlib
import logging
import os
import subprocess  # nosec B404 # subprocess needed for daemon management
import sys
import time
from pathlib import Path
from typing import Any

import click
import httpx
import psutil

from gobby.utils.status import fetch_rich_status, format_status_message

from .installers.service import (
    get_service_status,
    service_restart,
    service_start,
    service_stop,
)
from .utils import (
    _is_process_alive,
    find_web_dir,
    format_uptime,
    get_gobby_home,
    init_local_storage,
    is_port_available,
    kill_all_gobby_daemons,
    setup_logging,
    spawn_ui_server,
    wait_for_port_available,
)
from .utils import (
    stop_daemon as stop_daemon_util,
)

logger = logging.getLogger(__name__)


def _services_start(gobby_home: Path) -> None:
    """Start Docker services (Qdrant, Neo4j) via unified compose file.

    Uses Docker Compose profiles to start only installed services.
    Falls back to legacy per-service compose files during migration.
    """
    import shutil

    if not shutil.which("docker"):
        return

    services_dir = gobby_home / "services"
    compose_file = services_dir / "docker-compose.yml"

    # Fall back to legacy Neo4j-only compose if unified file doesn't exist yet
    if not compose_file.exists():
        legacy_compose = services_dir / "neo4j" / "docker-compose.yml"
        if legacy_compose.exists():
            compose_file = legacy_compose
        else:
            return

    # Build subprocess env with config resolved from bootstrap + DB config
    env = dict(os.environ)
    profiles: list[str] = []
    try:
        from gobby.config.app import load_config
        from gobby.config.bootstrap import load_bootstrap

        bootstrap = load_bootstrap()
        config = load_config()

        # Neo4j auth — read password directly from bootstrap
        env["GOBBY_NEO4J_PASSWORD"] = bootstrap.neo4j_password

        # Determine which profiles to start
        if config.databases.neo4j.url:
            profiles.append("neo4j")
        if config.databases.qdrant.url:
            profiles.append("qdrant")
    except Exception as e:
        logger.warning(f"Could not resolve config for services: {e}")
        # Default: try starting all profiles
        profiles = ["all"]

    if not profiles:
        logger.debug("No external services configured — skipping Docker startup")
        return

    cmd = ["docker", "compose", "-f", str(compose_file)]
    for profile in profiles:
        cmd.extend(["--profile", profile])
    cmd.extend(["up", "-d"])

    try:
        result = subprocess.run(  # nosec B603 B607 # hardcoded docker command
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=str(services_dir),
        )
        if result.returncode != 0:
            logger.warning(f"Failed to start services: {result.stderr or result.stdout}")
    except subprocess.TimeoutExpired:
        logger.warning("Timed out starting Docker services")
    except Exception as e:
        logger.warning(f"Failed to start Docker services: {e}")


def _services_stop(gobby_home: Path) -> None:
    """Stop all Docker services via unified compose file."""
    import shutil

    if not shutil.which("docker"):
        return

    services_dir = gobby_home / "services"
    compose_file = services_dir / "docker-compose.yml"

    # Fall back to legacy Neo4j-only compose
    if not compose_file.exists():
        legacy_compose = services_dir / "neo4j" / "docker-compose.yml"
        if legacy_compose.exists():
            compose_file = legacy_compose
        else:
            return

    try:
        result = subprocess.run(  # nosec B603 B607 # hardcoded docker command
            [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "down",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(services_dir),
        )
        if result.returncode != 0:
            logger.warning(f"Failed to stop services: {result.stderr or result.stdout}")
    except subprocess.TimeoutExpired:
        logger.warning("Timed out stopping Docker services")
    except Exception as e:
        logger.warning(f"Failed to stop Docker services: {e}")


@click.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose debug output",
)
@click.option(
    "--no-ui",
    is_flag=True,
    help="Disable auto-starting the web UI",
)
@click.option(
    "--docker",
    "docker_flag",
    is_flag=True,
    help="Also start Docker service containers (Qdrant, Neo4j)",
)
@click.pass_context
def start(ctx: click.Context, verbose: bool, no_ui: bool, docker_flag: bool) -> None:
    """Start the Gobby daemon."""
    # If OS service is installed, delegate to it
    svc = get_service_status()
    if svc.get("installed"):
        click.echo("Starting via OS service manager...")
        result = service_start()
        if result.get("success"):
            click.echo(f"Daemon started via {svc.get('platform', 'OS')} service")
            return
        click.echo(f"Service start failed: {result.get('error')}", err=True)
        click.echo("Falling back to direct start...")
    # Get config object
    config = ctx.obj["config"]

    # Get paths from config (respects GOBBY_HOME env var)
    gobby_dir = get_gobby_home()
    pid_file = gobby_dir / "gobby.pid"
    log_file = Path(config.telemetry.log_file).expanduser()
    error_log_file = Path(config.telemetry.log_file_error).expanduser()

    gobby_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    error_log_file.parent.mkdir(parents=True, exist_ok=True)

    # Initialize local storage before starting daemon
    click.echo("Initializing local storage...")
    init_local_storage()

    # Start Docker services (Qdrant, Neo4j) via unified compose
    services_compose = gobby_dir / "services" / "docker-compose.yml"
    legacy_compose = gobby_dir / "services" / "neo4j" / "docker-compose.yml"
    if services_compose.exists() or legacy_compose.exists() or docker_flag:
        click.echo("Starting Docker services...")
        _services_start(gobby_dir)

    # Kill any existing gobby daemon processes
    # Do this BEFORE the PID file check so orphaned processes that respawned
    # the daemon during restart don't cause a false "already running" error
    click.echo("Checking for existing gobby processes...")
    killed_count = kill_all_gobby_daemons()
    if killed_count > 0:
        click.echo(f"Stopped {killed_count} existing process(es)")
        # Clean up PID file — the process it referred to was likely among those killed
        pid_file.unlink(missing_ok=True)
        time.sleep(2.0)  # Wait for ports to be released
    else:
        click.echo("No existing processes found")

    # Check if already running (after sweep, so only truly independent instances remain)
    if pid_file.exists():
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())

            # Check if process is alive (handles zombies) AND is a gobby process
            if _is_process_alive(pid):
                try:
                    proc = psutil.Process(pid)
                    cmdline_str = " ".join(proc.cmdline())
                    if "gobby" in cmdline_str.lower():
                        click.echo(f"Gobby daemon is already running (PID: {pid})", err=True)
                        sys.exit(1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            # Stale PID file — process dead, zombie, or not gobby
            click.echo(f"Removing stale PID file (PID: {pid})")
            pid_file.unlink(missing_ok=True)
        except Exception:
            pid_file.unlink(missing_ok=True)

    # Check ports
    http_port = config.daemon_port
    ws_port = config.websocket.port

    if not is_port_available(http_port):
        click.echo(f"Waiting for HTTP port {http_port} to become available...", err=True)
        if not wait_for_port_available(http_port, timeout=5.0):
            click.echo(f"Error: Port {http_port} is still in use", err=True)
            sys.exit(1)

    if not is_port_available(ws_port):
        click.echo(f"Waiting for WebSocket port {ws_port} to become available...", err=True)
        if not wait_for_port_available(ws_port, timeout=5.0):
            click.echo(f"Error: Port {ws_port} is still in use", err=True)
            sys.exit(1)

    click.echo(f"Ports available (HTTP: {http_port}, WebSocket: {ws_port})")

    # Start the runner as a subprocess
    click.echo("Starting Gobby daemon...")

    # Build command
    cmd = [sys.executable, "-m", "gobby.runner"]
    if verbose:
        cmd.append("--verbose")

    # Open log files — ExitStack ensures cleanup even if second open() fails
    with contextlib.ExitStack() as log_stack:
        log_f = log_stack.enter_context(open(log_file, "a"))
        error_log_f = log_stack.enter_context(open(error_log_file, "a"))

        try:
            # Start detached subprocess
            process = subprocess.Popen(  # nosec B603 # cmd built from sys.executable and module path
                cmd,
                stdout=log_f,
                stderr=error_log_f,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from terminal
                env=os.environ.copy(),  # Inherit parent's environment (including PATH)
            )

            # Write PID file
            with open(pid_file, "w") as f:
                f.write(str(process.pid))

            # Give it a moment to start
            time.sleep(1.0)

            # Check if still running
            if process.poll() is not None:
                click.echo("Process exited immediately", err=True)
                click.echo(f"  Check logs: {error_log_file}", err=True)
                sys.exit(1)

            # Give server time to fully start
            time.sleep(2.0)

            # Display formatted status
            # Try to verify daemon is responding
            daemon_healthy = False
            start_time = time.time()
            max_wait = 120.0

            while (time.time() - start_time) < max_wait:
                try:
                    response = httpx.get(
                        f"http://localhost:{http_port}/api/admin/health", timeout=1.0
                    )
                    if response.status_code == 200:
                        daemon_healthy = True
                        break
                except (httpx.ConnectError, httpx.TimeoutException):
                    time.sleep(0.5)
                    continue

            # Spawn UI server if enabled
            ui_pid = None
            ui_url = None
            if daemon_healthy and not no_ui and config.ui.enabled:
                if config.ui.mode == "dev":
                    web_dir = find_web_dir(config)
                    if web_dir:
                        ui_log = Path(config.telemetry.log_file).expanduser().parent / "ui.log"
                        ui_pid = spawn_ui_server(config.ui.host, config.ui.port, web_dir, ui_log)
                        if ui_pid:
                            ui_url = f"http://{config.ui.host}:{config.ui.port}"
                            ui_pid_file = gobby_dir / "ui.pid"
                            with open(ui_pid_file, "w") as f:
                                f.write(str(ui_pid))
                    else:
                        click.echo("Warning: Web UI enabled but web/ directory not found")
                elif config.ui.mode == "production":
                    ui_url = f"http://localhost:{http_port}/"

            # Format and display status
            status_kwargs = {
                "running": daemon_healthy,
                "pid": process.pid,
                "pid_file": str(pid_file),
                "log_files": str(log_file.parent),
                "http_port": http_port,
                "websocket_port": ws_port,
                "ui_enabled": config.ui.enabled and not no_ui,
                "ui_mode": config.ui.mode if config.ui.enabled and not no_ui else None,
                "ui_url": ui_url,
                "ui_pid": ui_pid,
            }

            # Fetch rich status if daemon is healthy
            # Brief delay to allow stats to be computed
            if daemon_healthy:
                time.sleep(1.0)
                rich_status = asyncio.run(fetch_rich_status(http_port, timeout=2.0))
                status_kwargs.update(rich_status)

            message = format_status_message(**status_kwargs)
            click.echo("")
            click.echo(message)
            click.echo("")

            if not daemon_healthy:
                click.echo("Warning: Daemon started but health check failed")
                click.echo(f"  Check logs: {error_log_file}")

        except Exception as e:
            click.echo(f"Error starting daemon: {e}", err=True)
            sys.exit(1)


@click.command()
@click.option(
    "--docker",
    "docker_flag",
    is_flag=True,
    help="Also stop Docker service containers (Qdrant, Neo4j)",
)
@click.pass_context
def stop(ctx: click.Context, docker_flag: bool) -> None:
    """Stop the Gobby daemon."""
    # If OS service is installed and running, delegate to it
    docker_stopped = False
    svc = get_service_status()
    if svc.get("installed") and svc.get("running"):
        click.echo("Stopping via OS service manager...")
        result = service_stop()
        if result.get("success"):
            click.echo(f"Daemon stopped via {svc.get('platform', 'OS')} service")
        else:
            click.echo(f"Service stop failed: {result.get('error')}", err=True)
            click.echo("Falling back to direct stop...")

        # Stop Docker containers if requested
        if docker_flag:
            click.echo("Stopping Docker containers...")
            _services_stop(get_gobby_home())
            docker_stopped = True

        if result.get("success"):
            sys.exit(0)

    success = stop_daemon_util(quiet=False)

    # Stop Docker containers if requested (only if not already stopped above)
    if docker_flag and not docker_stopped:
        click.echo("Stopping Docker containers...")
        _services_stop(get_gobby_home())

    sys.exit(0 if success else 1)


@click.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose debug output",
)
@click.option(
    "--no-ui",
    is_flag=True,
    help="Disable auto-starting the web UI",
)
@click.option(
    "--docker",
    "docker_flag",
    is_flag=True,
    help="Also restart Docker service containers (Qdrant, Neo4j)",
)
@click.pass_context
def restart(ctx: click.Context, verbose: bool, no_ui: bool, docker_flag: bool) -> None:
    """Restart the Gobby daemon (stop then start)."""
    setup_logging(verbose)

    # If OS service is installed, delegate to it
    svc = get_service_status()
    if svc.get("installed") and svc.get("enabled"):
        click.echo(f"Restarting via {svc.get('platform', 'OS')} service manager...")
        result = service_restart()
        if result.get("success"):
            click.echo(f"Daemon restarted via {result.get('method', 'service manager')}")
            return
        click.echo(f"Service restart failed: {result.get('error')}", err=True)
        click.echo("Falling back to direct restart...")

    click.echo("Restarting Gobby daemon...")

    # Stop Docker containers if requested (before daemon stop)
    if docker_flag:
        click.echo("Stopping Docker containers...")
        _services_stop(get_gobby_home())

    # Stop daemon using helper function (doesn't call sys.exit)
    if not stop_daemon_util(quiet=False):
        click.echo("Failed to stop daemon, aborting restart", err=True)
        sys.exit(1)

    # Wait for cleanup and port release (TIME_WAIT state)
    time.sleep(3)

    # Call start command (with docker flag forwarded)
    ctx.invoke(start, verbose=verbose, no_ui=no_ui, docker_flag=docker_flag)


@click.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show Gobby daemon status and information."""
    config = ctx.obj["config"]
    pid_file = get_gobby_home() / "gobby.pid"
    log_dir = Path(config.telemetry.log_file).expanduser().parent

    # Read PID from file, falling back to launchctl service detection
    pid: int | None = None
    if pid_file.exists():
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None

    if pid is None:
        # No PID file — check if running as a launchctl service
        svc = get_service_status()
        if svc.get("running") and svc.get("pid"):
            pid = svc["pid"]
        else:
            message = format_status_message(running=False)
            click.echo(message)
            sys.exit(0)

    # Check if process is actually running
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        message = format_status_message(running=False)
        click.echo(message)
        click.echo(f"Note: Stale PID file found (PID {pid})")
        sys.exit(0)

    # Get process info for uptime (fallback)
    try:
        process = psutil.Process(pid)
        uptime_seconds = time.time() - process.create_time()
        uptime_str = format_uptime(uptime_seconds)
    except Exception:
        uptime_str = None

    http_port = config.daemon_port
    websocket_port = config.websocket.port

    # Check UI server status
    ui_enabled = config.ui.enabled
    ui_mode = config.ui.mode if ui_enabled else None
    ui_url = None
    ui_pid = None

    if ui_enabled:
        if ui_mode == "dev":
            ui_pid_file = get_gobby_home() / "ui.pid"
            if ui_pid_file.exists():
                try:
                    with open(ui_pid_file) as f:
                        _ui_pid = int(f.read().strip())
                    os.kill(_ui_pid, 0)
                    ui_pid = _ui_pid
                    ui_url = f"http://{config.ui.host}:{config.ui.port}"
                except (ProcessLookupError, ValueError, OSError):
                    pass  # UI server not running or stale PID file
        elif ui_mode == "production":
            ui_url = f"http://localhost:{http_port}/"

    # Build status kwargs
    status_kwargs: dict[str, Any] = {
        "running": True,
        "pid": pid,
        "pid_file": str(pid_file),
        "log_files": str(log_dir),
        "uptime": uptime_str,
        "http_port": http_port,
        "websocket_port": websocket_port,
        "ui_enabled": ui_enabled,
        "ui_mode": ui_mode,
        "ui_url": ui_url,
        "ui_pid": ui_pid,
    }

    # Fetch rich status from daemon API (includes Neo4j status)
    rich_status = asyncio.run(fetch_rich_status(http_port, timeout=2.0))
    status_kwargs.update(rich_status)

    # Add service info
    svc = get_service_status()
    if svc.get("installed"):
        parts = []
        if svc.get("running"):
            parts.append("running")
        elif svc.get("enabled"):
            parts.append("enabled")
        else:
            parts.append("disabled")
        parts.append(svc.get("platform", "unknown"))
        if svc.get("mode"):
            parts.append(f"{svc['mode']} mode")
        status_kwargs["service_info"] = f"installed ({', '.join(parts)})"

    # Format and display status
    message = format_status_message(**status_kwargs)
    click.echo(message)
    sys.exit(0)


def get_merge_status() -> dict[str, Any]:
    """
    Get the current merge status for status output.

    Returns:
        Dict with merge status info:
        - active: bool - Whether there's an active merge
        - resolution_id: str | None - ID of active resolution
        - source_branch: str | None - Source branch being merged
        - target_branch: str | None - Target branch
        - pending_conflicts: int - Number of unresolved conflicts
    """
    try:
        from gobby.storage.database import LocalDatabase
        from gobby.storage.merge_resolutions import MergeResolutionManager

        db = LocalDatabase()
        manager = MergeResolutionManager(db)

        resolution = manager.get_active_resolution()
        if not resolution:
            return {"active": False}

        conflicts = manager.list_conflicts(resolution_id=resolution.id)
        pending_count = sum(1 for c in conflicts if c.status == "pending")

        return {
            "active": True,
            "resolution_id": resolution.id,
            "source_branch": resolution.source_branch,
            "target_branch": resolution.target_branch,
            "pending_conflicts": pending_count,
            "total_conflicts": len(conflicts),
        }
    except Exception as e:
        logger.debug(f"Error getting merge status: {e}")
        return {"active": False, "error": str(e)}
