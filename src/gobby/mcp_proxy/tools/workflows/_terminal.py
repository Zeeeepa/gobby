"""
Terminal tools for workflows.
"""

from __future__ import annotations

import asyncio
import logging
import os
import stat
import subprocess  # nosec B404
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.paths import get_install_dir

if TYPE_CHECKING:
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)


async def close_terminal(
    session_id: str | None = None,
    session_manager: LocalSessionManager | None = None,
    signal: str = "TERM",
    delay_ms: int = 0,
) -> dict[str, Any]:
    """
    Close the current terminal by running the agent shutdown script.

    This is for agent self-termination (meeseeks-style). The agent calls
    this to close its own terminal window when done with its workflow.

    The script is located at ~/.gobby/scripts/agent_shutdown.sh and is
    automatically rebuilt if missing. It handles different terminal types
    (tmux, iTerm, Terminal.app, Ghostty, Kitty, WezTerm, etc.).

    Args:
        session_id: Session ID to look up terminal PID from. Accepts #N, N,
            UUID, or prefix. If provided with session_manager, the terminal
            PID is resolved from session.terminal_context.parent_pid.
        session_manager: LocalSessionManager for session lookups.
        signal: Signal to use for shutdown (TERM, KILL, INT). Default: TERM.
        delay_ms: Optional delay in milliseconds before shutdown. Default: 0.

    Returns:
        Dict with success status and message.
    """
    # Script location
    gobby_dir = Path.home() / ".gobby"
    scripts_dir = gobby_dir / "scripts"
    script_path = scripts_dir / "agent_shutdown.sh"

    # Source script from the install directory (single source of truth)
    source_script_path = get_install_dir() / "shared" / "scripts" / "agent_shutdown.sh"

    def get_script_version(script_content: str) -> str | None:
        """Extract VERSION marker from script content."""
        import re

        match = re.search(r"^# VERSION:\s*(.+)$", script_content, re.MULTILINE)
        return match.group(1).strip() if match else None

    # Ensure directories exist and script is present/up-to-date
    script_rebuilt = False
    try:
        scripts_dir.mkdir(parents=True, exist_ok=True)

        # Read source script content
        if source_script_path.exists():
            source_content = source_script_path.read_text()
            source_version = get_script_version(source_content)
        else:
            logger.warning(f"Source shutdown script not found at {source_script_path}")
            source_content = None
            source_version = None

        # Check if installed script exists and compare versions
        needs_rebuild = False
        if not script_path.exists():
            needs_rebuild = True
        elif source_content:
            installed_content = script_path.read_text()
            installed_version = get_script_version(installed_content)
            # Rebuild if versions differ or installed has no version marker
            if installed_version != source_version:
                needs_rebuild = True
                logger.info(
                    f"Shutdown script version mismatch: installed={installed_version}, source={source_version}"
                )

        if needs_rebuild:
            if not source_content:
                logger.error(
                    f"Cannot rebuild shutdown script at {script_path}: "
                    f"source script not found at {source_script_path}"
                )
                return {
                    "success": False,
                    "error": f"Source shutdown script not found at {source_script_path}",
                }
            script_path.write_text(source_content)
            # Make executable
            script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            script_rebuilt = True
            logger.info(f"Created/updated agent shutdown script at {script_path}")
    except OSError as e:
        return {
            "success": False,
            "error": f"Failed to create shutdown script: {e}",
        }

    # Validate signal
    valid_signals = {"TERM", "KILL", "INT", "HUP", "QUIT"}
    if signal.upper() not in valid_signals:
        return {
            "success": False,
            "error": f"Invalid signal '{signal}'. Valid: {valid_signals}",
        }

    # Apply delay before launching script (non-blocking)
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)

    # Resolve terminal PID from session context if available
    target_pid: int | None = None
    if session_id and session_manager:
        from gobby.mcp_proxy.tools.workflows._resolution import resolve_session_id

        try:
            resolved_id = resolve_session_id(session_manager, session_id)
            if resolved_id:
                session = session_manager.get(resolved_id)
                if session and session.terminal_context:
                    pid_value = session.terminal_context.get("parent_pid")
                    if pid_value is not None:
                        target_pid = int(pid_value)
                        logger.info(f"Resolved terminal PID {target_pid} from session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to resolve terminal PID from session: {e}")

    # Launch the script
    try:
        # Run in background - we don't wait for it since it kills our process
        env = os.environ.copy()

        # Pass PID as first arg if available, otherwise script will discover via PPID
        pid_arg = str(target_pid) if target_pid else ""
        subprocess.Popen(  # nosec B603 - script path is from gobby scripts directory
            [str(script_path), pid_arg, signal.upper(), "0"],  # Delay already applied
            env=env,
            start_new_session=True,  # Detach from parent
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        result: dict[str, Any] = {
            "success": True,
            "message": "Shutdown script launched",
            "script_path": str(script_path),
            "script_rebuilt": script_rebuilt,
            "signal": signal.upper(),
        }
        if target_pid:
            result["target_pid"] = target_pid
            result["pid_source"] = "session_terminal_context"
        else:
            result["pid_source"] = "ppid_discovery"
        return result
    except OSError as e:
        return {
            "success": False,
            "error": f"Failed to launch shutdown script: {e}",
        }
