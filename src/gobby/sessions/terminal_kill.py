"""Terminal session kill utility.

Provides kill_terminal_session() for terminating CLI sessions via their
terminal context (tmux pane or PID). Extracted from session_control.py
for reuse by HTTP routes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

logger = logging.getLogger(__name__)


async def kill_terminal_session(terminal_ctx: dict[str, Any], session_id: str) -> bool:
    """Kill a plain terminal CLI session using its terminal context.

    Tries tmux pane kill first (cleanest — kills just that pane), then
    falls back to PID-based SIGTERM.

    Args:
        terminal_ctx: Session's terminal_context dict (tmux_pane, parent_pid, etc.)
        session_id: Session ID for logging.

    Returns:
        True if any kill method succeeded.
    """
    # 1. Try tmux pane kill (sends SIGHUP to process in pane)
    tmux_pane = terminal_ctx.get("tmux_pane")
    if tmux_pane:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "kill-pane",
                "-t",
                str(tmux_pane),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                logger.info(
                    "Killed terminal session %s via tmux pane %s",
                    session_id[:8],
                    tmux_pane,
                )
                return True
            else:
                logger.debug(
                    "tmux kill-pane failed for %s: %s",
                    tmux_pane,
                    stderr.decode().strip() if stderr else "unknown",
                )
        except TimeoutError:
            logger.warning("tmux kill-pane timed out for pane %s", tmux_pane)
        except FileNotFoundError:
            logger.debug("tmux not available, skipping pane kill")
        except Exception as e:
            logger.warning("tmux kill-pane error for %s: %s", tmux_pane, e)

    # 2. Fallback: PID-based kill
    parent_pid = terminal_ctx.get("parent_pid")
    if parent_pid:
        try:
            pid = int(parent_pid)
            os.kill(pid, signal.SIGTERM)
            logger.info(
                "Killed terminal session %s via SIGTERM to PID %d",
                session_id[:8],
                pid,
            )
            return True
        except ProcessLookupError:
            logger.debug("PID %s already dead for session %s", parent_pid, session_id[:8])
        except (ValueError, OSError) as e:
            logger.warning("PID kill failed for session %s: %s", session_id[:8], e)

    logger.debug(
        "No kill method available for session %s (no tmux_pane or parent_pid)",
        session_id[:8],
    )
    return False
