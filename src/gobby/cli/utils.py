"""
Shared utilities for CLI commands.
"""

import logging
import os
import signal
import time
from pathlib import Path

import click
import psutil

from gobby.config.app import load_config
from gobby.storage.database import LocalDatabase
from gobby.storage.projects import LocalProjectManager
from gobby.storage.sessions import LocalSessionManager
from gobby.utils.project_context import get_project_context

logger = logging.getLogger(__name__)


def get_gobby_home() -> Path:
    """Get gobby home directory, respecting GOBBY_HOME env var.

    Returns:
        Path to gobby home (~/.gobby by default, or GOBBY_HOME if set)
    """
    gobby_home = os.environ.get("GOBBY_HOME")
    if gobby_home:
        return Path(gobby_home)
    return Path.home() / ".gobby"


def get_resources_dir(project_path: str | None = None) -> Path:
    """Get the resources directory for storing media files.

    If a project path is provided, returns the project-local resources directory
    (.gobby/resources/ within the project). Otherwise, returns the global
    resources directory (~/.gobby/resources/).

    The directory is created if it doesn't exist.

    Args:
        project_path: Optional project root path for project-local resources

    Returns:
        Path to the resources directory
    """
    if project_path:
        resources_dir = Path(project_path) / ".gobby" / "resources"
    else:
        resources_dir = get_gobby_home() / "resources"

    # Ensure directory exists
    resources_dir.mkdir(parents=True, exist_ok=True)
    return resources_dir


def resolve_project_ref(project_ref: str | None, exit_on_not_found: bool = True) -> str | None:
    """Resolve a project reference (name or UUID) to project ID.

    Accepts:
    - Project name (e.g., "gobby")
    - Project UUID
    - None (returns current project from context)

    Args:
        project_ref: Project name, UUID, or None
        exit_on_not_found: If True (default), exit the CLI when an explicit
            project_ref is provided but not found

    Returns:
        Project ID string, or None if not found/no context
    """
    if not project_ref:
        # Use current project context
        ctx = get_project_context()
        return ctx.get("id") if ctx else None

    db = LocalDatabase()
    try:
        manager = LocalProjectManager(db)

        # Try as direct UUID first
        project = manager.get(project_ref)
        if project:
            return project.id

        # Try as project name
        project = manager.get_by_name(project_ref)
        if project:
            return project.id
    finally:
        db.close()

    return None


def get_active_session_id(db: LocalDatabase | None = None) -> str | None:
    """Get the most recent active session ID."""
    close_db = False
    if db is None:
        db = LocalDatabase()
        close_db = True

    try:
        # SELECT id FROM sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1
        # Using format compatible with the rest of the codebase (raw SQL) to avoid circular imports
        # if using session manager directly which might pull in other things.
        # But we import LocalSessionManager at top, so let's use it if possible or raw SQL for speed.
        row = db.fetchone(
            "SELECT id FROM sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        )
        return row["id"] if row else None
    finally:
        if close_db:
            db.close()


def resolve_session_id(session_ref: str | None, project_id: str | None = None) -> str:
    """
    Resolve session reference to UUID.

    Centralized logic used by all CLI commands.

    Args:
        session_ref: User input string (UUID, #N, N, prefix) or None
        project_id: Project ID for project-scoped #N lookup.
            If not provided, auto-detected from current project context.

    Returns:
        Resolved UUID string

    Raises:
        click.ClickException: If session not found or ambiguous
    """
    db = LocalDatabase()
    try:
        # If no reference provided, try to find active session
        if not session_ref:
            active_id = get_active_session_id(db)
            if not active_id:
                raise click.ClickException("No active session found. Specify --session.")
            return active_id

        # Get project_id from context if not provided
        if not project_id:
            ctx = get_project_context()
            project_id = ctx.get("id") if ctx else None

        # Use SessionManager for resolution logic
        manager = LocalSessionManager(db)
        try:
            return manager.resolve_session_reference(session_ref, project_id)
        except ValueError as e:
            raise click.ClickException(str(e)) from None
    finally:
        db.close()


def list_project_names() -> list[str]:
    """List all project names for shell completion."""
    db = LocalDatabase()
    try:
        manager = LocalProjectManager(db)
        return [p.name for p in manager.list()]
    finally:
        db.close()


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for CLI.

    Args:
        verbose: If True, enable DEBUG level logging
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def format_uptime(seconds: float) -> str:
    """
    Format uptime in human-readable format.

    Args:
        seconds: Uptime in seconds

    Returns:
        Formatted string like "1h 23m 45s"
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def is_port_available(port: int, host: str = "localhost") -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host address to bind to

    Returns:
        True if port is available, False otherwise
    """
    import socket

    # Try to bind to the port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        sock.close()
        return False


def wait_for_port_available(port: int, host: str = "localhost", timeout: float = 5.0) -> bool:
    """
    Wait for a port to become available.

    Args:
        port: Port number to check
        host: Host address to bind to
        timeout: Maximum time to wait in seconds

    Returns:
        True if port became available, False if timeout
    """
    start_time = time.time()

    while (time.time() - start_time) < timeout:
        if is_port_available(port, host):
            return True
        time.sleep(0.1)

    return False


def kill_all_gobby_daemons() -> int:
    """
    Find and kill all gobby DAEMON processes (not CLI commands).

    Only kills processes that are actually running daemon servers,
    not CLI invocations or other tools.

    Detection methods:
    1. Matches gobby.runner (the main daemon process)
    2. Matches processes listening on daemon ports (60887/60888)

    Returns:
        Number of processes killed
    """
    # Load config to get the configured ports
    try:
        config = load_config(create_default=False)
        http_port = config.daemon_port
        ws_port = config.websocket.port
    except Exception:
        # Fallback to defaults if config can't be loaded
        http_port = 60887
        ws_port = 60888

    killed_count = 0
    current_pid = os.getpid()
    parent_pid = os.getppid()

    # Get our parent process tree to avoid killing it
    parent_pids = {current_pid, parent_pid}
    try:
        parent_proc = psutil.Process(parent_pid)
        while parent_proc.parent() is not None:
            parent_proc = parent_proc.parent()
            parent_pids.add(parent_proc.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # Find all gobby daemon processes
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            # Skip our own process and parent tree
            if proc.pid in parent_pids:
                continue

            # Check if this is a gobby daemon process
            cmdline = proc.cmdline()
            cmdline_str = " ".join(cmdline)

            # Match gobby.runner which is the actual daemon process
            # Started via: python -m gobby.runner
            is_gobby_daemon = (
                "python" in cmdline_str.lower()
                and (
                    # Match gobby.runner (new package)
                    "gobby.runner" in cmdline_str
                    # Also match legacy gobby_client.runner if it exists
                    or "gobby_client.runner" in cmdline_str
                )
                # Exclude CLI invocations
                and "gobby.cli" not in cmdline_str
                and "gobby_client.cli" not in cmdline_str
            )

            # Also check for processes that might be old daemon instances
            # by checking if they're listening on our ports
            if not is_gobby_daemon:
                try:
                    # Check if process has connections on daemon ports
                    connections = proc.connections()
                    for conn in connections:
                        if hasattr(conn, "laddr") and conn.laddr:
                            if conn.laddr.port in [http_port, ws_port]:
                                # Only consider it a daemon if it's a Python process
                                # to avoid killing unrelated services
                                if "python" in cmdline_str.lower():
                                    is_gobby_daemon = True
                                    break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass

            if is_gobby_daemon:
                click.echo(f"Found gobby daemon (PID {proc.pid}): {cmdline_str[:100]}")

                # Try graceful shutdown first (SIGTERM)
                try:
                    proc.send_signal(signal.SIGTERM)
                    # Wait up to 5 seconds for graceful shutdown
                    proc.wait(timeout=5)
                    click.echo(f"Gracefully stopped PID {proc.pid}")
                    killed_count += 1
                except psutil.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    click.echo(f"Process {proc.pid} didn't stop gracefully, force killing...")
                    proc.kill()
                    proc.wait(timeout=2)
                    click.echo(f"Force killed PID {proc.pid}")
                    killed_count += 1

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process already gone or we can't access it
            pass
        except Exception as e:
            click.echo(f"Warning: Error checking process {proc.pid}: {e}", err=True)

    return killed_count


def init_local_storage() -> None:
    """Initialize hub SQLite storage and run migrations."""
    from gobby.storage.database import LocalDatabase
    from gobby.storage.migrations import run_migrations

    config = load_config(create_default=False)
    hub_db_path = Path(config.database_path).expanduser()

    # Ensure hub db directory exists
    hub_db_path.parent.mkdir(parents=True, exist_ok=True)

    hub_db = LocalDatabase(hub_db_path)
    run_migrations(hub_db)
    logger.debug(f"Database: {hub_db_path}")


def get_install_dir() -> Path:
    """Get the gobby install directory.

    Checks for source directory (development mode) first,
    falls back to package directory.

    Returns:
        Path to the install directory
    """
    # Import from centralized paths module to avoid duplication
    from gobby.paths import get_install_dir as _get_install_dir

    return _get_install_dir()


def _is_process_alive(pid: int) -> bool:
    """Check if a process is truly alive (not zombie, not dead).

    Uses psutil to check process status, which handles zombies correctly.
    os.kill(pid, 0) succeeds on zombie processes, but they're effectively dead.

    Args:
        pid: Process ID to check

    Returns:
        True only if process exists and is not a zombie
    """
    try:
        proc = psutil.Process(pid)
        return bool(proc.status() != psutil.STATUS_ZOMBIE)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def stop_daemon(quiet: bool = False) -> bool:
    """Stop the daemon process. Returns True on success, False on failure.

    Args:
        quiet: If True, suppress output messages

    Returns:
        True if daemon was stopped successfully or wasn't running, False on error
    """
    pid_file = get_gobby_home() / "gobby.pid"

    # Read PID from file
    if not pid_file.exists():
        if not quiet:
            click.echo("Gobby daemon is not running (no PID file found)")
        return True

    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
    except Exception as e:
        if not quiet:
            click.echo(f"Error reading PID file: {e}", err=True)
        pid_file.unlink(missing_ok=True)
        return False

    # Check if process is actually running (handles zombies correctly)
    if not _is_process_alive(pid):
        if not quiet:
            click.echo(f"Gobby daemon is not running (stale PID file with PID {pid})")
        pid_file.unlink(missing_ok=True)
        return True

    try:
        # Send SIGTERM signal for graceful shutdown
        os.kill(pid, signal.SIGTERM)
        if not quiet:
            click.echo(f"Sent shutdown signal to Gobby daemon (PID {pid})")

        # Wait for graceful shutdown
        # Match daemon's uvicorn timeout_graceful_shutdown (15s) + buffer
        max_wait = 20
        for _ in range(max_wait * 10):
            time.sleep(0.1)
            if not _is_process_alive(pid):
                if not quiet:
                    click.echo("Gobby daemon stopped successfully")
                pid_file.unlink(missing_ok=True)
                return True

        # Process didn't stop gracefully - try force kill
        if not quiet:
            click.echo(f"Process didn't stop gracefully after {max_wait}s, force killing...")

        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
        except ProcessLookupError:
            pass  # Already dead

        # Final check
        if not _is_process_alive(pid):
            if not quiet:
                click.echo("Gobby daemon force killed successfully")
            pid_file.unlink(missing_ok=True)
            return True

        if not quiet:
            click.echo("Warning: Failed to stop process", err=True)
        return False

    except PermissionError:
        if not quiet:
            click.echo(f"Error: Permission denied to stop process (PID {pid})", err=True)
        return False

    except ProcessLookupError:
        # Process died between our check and sending signal - that's fine
        if not quiet:
            click.echo("Gobby daemon stopped")
        pid_file.unlink(missing_ok=True)
        return True

    except Exception as e:
        if not quiet:
            click.echo(f"Error stopping daemon: {e}", err=True)
        return False
