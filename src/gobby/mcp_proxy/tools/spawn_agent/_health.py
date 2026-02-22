"""Health check utilities for spawned agents."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil

logger = logging.getLogger(__name__)

# Track fire-and-forget health check tasks for clean shutdown
_health_check_tasks: set[asyncio.Task[None]] = set()


def cancel_health_checks() -> None:
    """Cancel all pending health check tasks (call on shutdown)."""
    for task in _health_check_tasks:
        task.cancel()
    _health_check_tasks.clear()


# Seconds to wait before checking if tmux session survived spawn.
# Configurable via GOBBY_TMUX_HEALTH_CHECK_DELAY env var.
try:
    TMUX_HEALTH_CHECK_DELAY = float(os.environ.get("GOBBY_TMUX_HEALTH_CHECK_DELAY", "0.5"))
except (ValueError, TypeError):
    TMUX_HEALTH_CHECK_DELAY = 0.5


async def _check_tmux_session_alive(
    session_name: str,
    socket_name: str | None = None,
) -> bool:
    """Check if a tmux session is still alive after spawn."""
    tmux_bin = shutil.which("tmux")
    if not tmux_bin:
        return True  # Can't check without tmux binary, assume alive
    try:
        cmd = [tmux_bin]
        if socket_name:
            cmd.extend(["-L", socket_name])
        cmd.extend(["has-session", "-t", session_name])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        return proc.returncode == 0
    except TimeoutError:
        proc.kill()
        await proc.wait()  # Reap the process to avoid zombie
        return True  # Timed out, assume alive
    except asyncio.CancelledError:
        raise
    except OSError:
        return True  # If check itself fails, don't false-positive
