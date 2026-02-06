"""
In-memory registry for tracking running agent processes.

This module provides thread-safe tracking of running agents that complements
the database storage. It tracks runtime information like PIDs and process handles
that shouldn't be persisted.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Event callback type - (event_type, run_id, data)
EventCallback = Callable[[str, str, dict[str, Any]], None]

# Validation patterns for terminal context values passed to subprocess calls
_TERMINAL_CTX_PATTERNS: dict[str, re.Pattern[str]] = {
    "tmux_pane": re.compile(r"^%\d+$"),
    "kitty_window_id": re.compile(r"^\d+$"),
    "alacritty_socket": re.compile(r"^[a-zA-Z0-9/_.\-]+$"),
    "iterm_session_id": re.compile(r"^[a-zA-Z0-9_\-:.]+$"),
    "parent_pid": re.compile(r"^\d+$"),
    "session_id": re.compile(r"^[a-zA-Z0-9_\-]+$"),
}


def _validate_terminal_value(key: str, value: str) -> bool:
    """Validate a terminal context value against its expected format.

    Returns True if the value matches the expected pattern for the given key.
    """
    pattern = _TERMINAL_CTX_PATTERNS.get(key)
    if pattern is None:
        return False
    return pattern.fullmatch(str(value)) is not None


@dataclass
class RunningAgent:
    """
    In-memory record of a running agent process.

    Tracks runtime state that isn't appropriate for database storage.
    """

    run_id: str
    """Agent run ID (matches database record)."""

    session_id: str
    """Child session ID for this agent."""

    parent_session_id: str
    """Parent session that spawned this agent."""

    mode: str
    """Execution mode: in_process, terminal, embedded, headless."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """When the agent started running."""

    # Process tracking (for terminal/embedded/headless modes)
    pid: int | None = None
    """Process ID if running externally."""

    master_fd: int | None = None
    """PTY master file descriptor (embedded mode only)."""

    terminal_type: str | None = None
    """Terminal type (ghostty, iterm, etc.) for terminal mode."""

    # State tracking
    provider: str = "claude"
    """LLM provider being used."""

    workflow_name: str | None = None
    """Workflow being executed, if any."""

    worktree_id: str | None = None
    """Associated worktree, if any."""

    # In-process agent tracking
    task: Any | None = None
    """Async task object for in-process agents (asyncio.Task)."""

    monitor_task: Any | None = None
    """Background monitoring task for headless agents (asyncio.Task)."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "mode": self.mode,
            "started_at": self.started_at.isoformat(),
            "pid": self.pid,
            "master_fd": self.master_fd,
            "terminal_type": self.terminal_type,
            "provider": self.provider,
            "workflow_name": self.workflow_name,
            "worktree_id": self.worktree_id,
            "has_task": self.task is not None,
        }


class RunningAgentRegistry:
    """
    Thread-safe registry for tracking running agents.

    This registry tracks agents that are currently executing, whether
    in-process or in external processes (terminal/headless). It provides:

    - Thread-safe add/get/remove operations
    - Lookup by run_id, session_id, or parent_session_id
    - PID-based lookup for process management
    - Cleanup of stale entries

    Example:
        >>> registry = RunningAgentRegistry()
        >>> agent = RunningAgent(
        ...     run_id="ar-123",
        ...     session_id="sess-456",
        ...     parent_session_id="sess-parent",
        ...     mode="terminal",
        ...     pid=12345,
        ... )
        >>> registry.add(agent)
        >>> registry.get("ar-123")
        RunningAgent(...)
        >>> registry.remove("ar-123")
    """

    def __init__(self) -> None:
        """Initialize the registry with an empty agents dict and lock."""
        self._agents: dict[str, RunningAgent] = {}
        self._lock = threading.RLock()
        self._logger = logger
        self._event_callbacks: list[EventCallback] = []
        self._event_callbacks_lock = threading.Lock()

    def add_event_callback(self, callback: EventCallback) -> None:
        """
        Add an event callback for agent lifecycle events.

        Callbacks are invoked when agents are added or removed.

        Args:
            callback: Function that receives (event_type, run_id, data)
        """
        with self._event_callbacks_lock:
            self._event_callbacks.append(callback)

    def emit_event(self, event_type: str, run_id: str, data: dict[str, Any]) -> None:
        """
        Emit a custom event to all registered callbacks.

        Args:
            event_type: Type of event (e.g., terminal_output)
            run_id: Agent run ID
            data: Additional event data
        """
        self._emit_event(event_type, run_id, data)

    def _emit_event(self, event_type: str, run_id: str, data: dict[str, Any]) -> None:
        """
        Emit an event to all registered callbacks.

        Args:
            event_type: Type of event (agent_started, agent_completed, etc.)
            run_id: Agent run ID
            data: Additional event data
        """
        # Take a snapshot of callbacks under lock, then iterate outside lock
        with self._event_callbacks_lock:
            callbacks = list(self._event_callbacks)
        for callback in callbacks:
            try:
                callback(event_type, run_id, data)
            except Exception as e:
                self._logger.warning(f"Event callback error: {e}")

    def add(self, agent: RunningAgent) -> None:
        """
        Add a running agent to the registry.

        Args:
            agent: The running agent to track.
        """
        with self._lock:
            self._agents[agent.run_id] = agent
            self._logger.debug(
                f"Registered running agent {agent.run_id} (mode={agent.mode}, pid={agent.pid})"
            )
        # Emit event outside lock
        self._emit_event(
            "agent_started",
            agent.run_id,
            {
                "session_id": agent.session_id,
                "parent_session_id": agent.parent_session_id,
                "mode": agent.mode,
                "provider": agent.provider,
                "pid": agent.pid,
            },
        )

    def get(self, run_id: str) -> RunningAgent | None:
        """
        Get a running agent by run ID.

        Args:
            run_id: The agent run ID.

        Returns:
            The RunningAgent if found, None otherwise.
        """
        with self._lock:
            return self._agents.get(run_id)

    def remove(self, run_id: str, status: str = "completed") -> RunningAgent | None:
        """
        Remove a running agent from the registry.

        Args:
            run_id: The agent run ID to remove.
            status: Final status (completed, failed, cancelled, timeout).

        Returns:
            The removed RunningAgent if found, None otherwise.
        """
        with self._lock:
            agent = self._agents.pop(run_id, None)
            if agent:
                self._logger.debug(f"Unregistered running agent {run_id}")
        # Emit event outside lock
        if agent:
            self._emit_event(
                f"agent_{status}",
                run_id,
                {
                    "session_id": agent.session_id,
                    "parent_session_id": agent.parent_session_id,
                    "mode": agent.mode,
                    "provider": agent.provider,
                },
            )
        return agent

    def _close_terminal_window(
        self,
        agent: RunningAgent,
        signal_name: str = "TERM",
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """
        Close the terminal window/pane using OS-agnostic methods.

        Tries multiple strategies based on terminal type and available context.

        Args:
            agent: The running agent with terminal context
            signal_name: Signal to use if falling back to PID kill
            timeout: Timeout for subprocess operations

        Returns:
            Dict with success status and method used
        """
        import os
        import signal
        import subprocess  # nosec B404
        import sys

        is_macos = sys.platform == "darwin"
        is_windows = sys.platform == "win32"

        # Get session terminal context
        ctx: dict[str, Any] = {}
        try:
            from gobby.storage.database import LocalDatabase
            from gobby.storage.sessions import LocalSessionManager

            db = LocalDatabase()
            session_mgr = LocalSessionManager(db)
            session = session_mgr.get(agent.session_id)
            if session and session.terminal_context:
                ctx = session.terminal_context
        except Exception as e:
            self._logger.debug(f"Failed to get terminal context: {e}")

        term_program = ctx.get("term_program", "").lower()

        # Validate terminal context values - remove invalid ones to prevent injection
        for _key in ("tmux_pane", "kitty_window_id", "alacritty_socket",
                      "iterm_session_id", "parent_pid"):
            _val = ctx.get(_key)
            if _val is not None and not _validate_terminal_value(_key, str(_val)):
                self._logger.warning(f"Invalid {_key} format: {_val!r}, ignoring")
                ctx.pop(_key, None)

        # Validate session_id for pgrep-based strategies
        _valid_session_id = _validate_terminal_value("session_id", agent.session_id)
        if not _valid_session_id:
            self._logger.warning(
                f"Invalid session_id format for pgrep, skipping: {agent.session_id!r}"
            )

        # === Cross-platform strategies (try first) ===

        # Strategy 1: tmux (macOS + Linux) - most reliable
        # Only use tmux if the pane actually exists and belongs to a running tmux session
        if ctx.get("tmux_pane"):
            try:
                # Verify the pane exists before killing - prevents killing inherited/stale panes
                verify_result = subprocess.run(  # nosec B603 B607 - hardcoded tmux command
                    ["tmux", "display-message", "-t", ctx["tmux_pane"], "-p", "#{pane_id}"],
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                )
                if verify_result.returncode == 0 and verify_result.stdout.strip():
                    subprocess.run(  # nosec B603 B607 - hardcoded tmux command
                        ["tmux", "kill-pane", "-t", ctx["tmux_pane"]],
                        timeout=timeout,
                        capture_output=True,
                    )
                    return {"success": True, "method": "tmux_kill_pane", "pane": ctx["tmux_pane"]}
                else:
                    self._logger.debug(
                        f"tmux pane {ctx['tmux_pane']} not found or not accessible, skipping"
                    )
            except Exception as e:
                self._logger.debug(f"tmux kill-pane failed: {e}")

        # Strategy 2: Kitty remote control (cross-platform)
        if term_program == "kitty" and ctx.get("kitty_window_id"):
            try:
                subprocess.run(  # nosec B603 B607 - hardcoded kitty command
                    ["kitty", "@", "close-window", "--match", f"id:{ctx['kitty_window_id']}"],
                    timeout=timeout,
                    capture_output=True,
                )
                return {
                    "success": True,
                    "method": "kitty_remote",
                    "window_id": ctx["kitty_window_id"],
                }
            except Exception as e:
                self._logger.debug(f"kitty remote failed: {e}")

        # Strategy 3: Alacritty socket IPC (cross-platform)
        if term_program == "alacritty" and ctx.get("alacritty_socket"):
            try:
                subprocess.run(  # nosec B603 B607 - hardcoded alacritty command
                    ["alacritty", "msg", "--socket", ctx["alacritty_socket"], "close"],
                    timeout=timeout,
                    capture_output=True,
                )
                return {"success": True, "method": "alacritty_socket"}
            except Exception as e:
                self._logger.debug(f"alacritty socket failed: {e}")

        # === macOS-specific strategies ===

        if is_macos:
            # Strategy 4: iTerm AppleScript
            if "iterm" in term_program and ctx.get("iterm_session_id"):
                try:
                    script = f'tell app "iTerm2" to close (session id "{ctx["iterm_session_id"]}")'
                    subprocess.run(  # nosec B603 B607 - osascript is safe, args built from config
                        ["osascript", "-e", script],
                        timeout=timeout,
                        capture_output=True,
                    )
                    return {"success": True, "method": "iterm_applescript"}
                except Exception as e:
                    self._logger.debug(f"iTerm AppleScript failed: {e}")

            # Strategy 5: Terminal.app AppleScript
            if term_program == "apple_terminal" or "terminal" in term_program:
                try:
                    # Close window by matching the session process
                    script = 'tell app "Terminal" to close front window'
                    subprocess.run(  # nosec B603 B607 - osascript with internal AppleScript
                        ["osascript", "-e", script],
                        timeout=timeout,
                        capture_output=True,
                    )
                    return {"success": True, "method": "terminal_applescript"}
                except Exception as e:
                    self._logger.debug(f"Terminal.app AppleScript failed: {e}")

            # Strategy 6: Ghostty - find window by session_id in process args
            if "ghostty" in term_program and _valid_session_id:
                try:
                    # Ghostty doesn't have remote control, but we can find its window process
                    result = subprocess.run(  # nosec B603 B607 - pgrep with validated session_id
                        ["pgrep", "-f", f"ghostty.*{agent.session_id}"],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        pid = int(result.stdout.strip().split("\n")[0])
                        os.kill(pid, signal.SIGTERM)
                        return {"success": True, "method": "ghostty_pgrep", "pid": pid}
                except Exception as e:
                    self._logger.debug(f"Ghostty pgrep failed: {e}")

        # === Windows-specific strategies ===

        if is_windows:
            parent_pid = ctx.get("parent_pid")
            if parent_pid:
                try:
                    # /T kills the entire process tree
                    subprocess.run(  # nosec B603 B607 - hardcoded taskkill command
                        ["taskkill", "/F", "/T", "/PID", str(parent_pid)],
                        timeout=timeout,
                        capture_output=True,
                    )
                    return {"success": True, "method": "taskkill_tree", "pid": parent_pid}
                except Exception as e:
                    self._logger.debug(f"taskkill failed: {e}")

        # === Generic fallback strategies ===

        # Strategy 7: pgrep for terminal with session_id in args (macOS + Linux)
        if not is_windows and term_program and _valid_session_id:
            try:
                result = subprocess.run(  # nosec B603 B607 - pgrep with validated session_id
                    ["pgrep", "-f", f"{term_program}.*{agent.session_id}"],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode == 0 and result.stdout.strip():
                    pid = int(result.stdout.strip().split("\n")[0])
                    os.kill(pid, signal.SIGTERM)
                    return {"success": True, "method": "terminal_pgrep", "pid": pid}
            except Exception as e:
                self._logger.debug(f"terminal pgrep failed: {e}")

        # Strategy 8: Kill parent_pid directly (closes terminal on most systems)
        parent_pid = ctx.get("parent_pid")
        if parent_pid:
            try:
                pid = int(parent_pid)
                if is_windows:
                    subprocess.run(  # nosec B603 B607 - hardcoded taskkill command
                        ["taskkill", "/F", "/PID", str(pid)],
                        timeout=timeout,
                        capture_output=True,
                    )
                else:
                    os.kill(pid, signal.SIGTERM)
                return {"success": True, "method": "parent_pid", "pid": pid}
            except (ProcessLookupError, OSError, ValueError) as e:
                self._logger.debug(f"parent_pid kill failed: {e}")

        return {"success": False, "error": "No terminal close method available"}

    def kill(
        self,
        run_id: str,
        signal_name: str = "TERM",
        timeout: float = 5.0,
        close_terminal: bool = False,
    ) -> dict[str, Any]:
        """
        Kill a running agent process.

        Strategy varies by mode:
        - headless: Direct signal to tracked PID
        - terminal: Check terminal_context for PID, fallback to pgrep
        - embedded: Close PTY fd + signal
        - in_process: Cancel asyncio task

        Args:
            run_id: Agent run ID
            signal_name: Signal without SIG prefix (TERM, KILL)
            timeout: Seconds before escalating TERM → KILL
            close_terminal: If True, attempt to close the terminal window/pane
                instead of just killing the agent process (for self-termination)

        Returns:
            Dict with success status and details
        """
        import os
        import signal
        import subprocess  # nosec B404 - subprocess needed for process management
        import time

        agent = self.get(run_id)
        if not agent:
            return {"success": False, "error": "Agent not found in registry"}

        # Handle in_process mode (asyncio.Task)
        if agent.mode == "in_process" and agent.task:
            agent.task.cancel()
            self.remove(run_id, status="cancelled")
            return {"success": True, "message": "Cancelled in-process task"}

        # For terminal mode with close_terminal=True, try terminal-specific close methods
        if close_terminal and agent.mode == "terminal" and agent.session_id:
            result = self._close_terminal_window(agent, signal_name, timeout)
            if result.get("success"):
                self.remove(run_id, status="killed")
                return result
            # Fall through to standard kill if terminal close failed

        # For terminal mode, find PID via multiple strategies
        target_pid = agent.pid
        found_via = "registry"

        if agent.mode == "terminal" and agent.session_id:
            # Strategy 1: Check session's terminal_context (Claude hooks)
            try:
                from gobby.storage.database import LocalDatabase
                from gobby.storage.sessions import LocalSessionManager

                db = LocalDatabase()
                session_mgr = LocalSessionManager(db)
                session = session_mgr.get(agent.session_id)
                if session and session.terminal_context:
                    ctx_pid = session.terminal_context.get("parent_pid")
                    if ctx_pid:
                        target_pid = int(ctx_pid)
                        found_via = "terminal_context"
                        self._logger.info(f"Found PID from session terminal_context: {target_pid}")
            except Exception as e:
                self._logger.debug(f"terminal_context lookup failed: {e}")

            # Strategy 2: pgrep fallback (for Codex/Gemini without hooks)
            if found_via == "registry" or not target_pid:
                # Validate session_id format (UUID or safe identifier) to prevent injection
                session_id_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
                if not session_id_pattern.match(agent.session_id):
                    self._logger.warning(
                        f"Invalid session_id format, skipping pgrep: {agent.session_id}"
                    )
                else:
                    try:
                        # Use -- to prevent pgrep from interpreting pattern as options
                        pgrep_result = subprocess.run(  # nosec B603 B607 - pgrep with validated session_id
                            ["pgrep", "-f", "--", f"session-id {agent.session_id}"],
                            capture_output=True,
                            text=True,
                            timeout=5.0,
                        )
                        if pgrep_result.returncode == 0 and pgrep_result.stdout.strip():
                            pids = pgrep_result.stdout.strip().split("\n")
                            if len(pids) == 1:
                                target_pid = int(pids[0])
                                found_via = "pgrep"
                                self._logger.info(f"Found PID via pgrep: {target_pid}")
                            else:
                                # Multiple PIDs found - need to disambiguate
                                self._logger.warning(
                                    f"pgrep returned {len(pids)} PIDs for session "
                                    f"{agent.session_id}: {pids}"
                                )
                                # Inspect each candidate to find the correct one
                                matched_pid = None
                                for pid_str in pids:
                                    try:
                                        candidate_pid = int(pid_str)
                                        # Query the process command line to verify
                                        ps_result = subprocess.run(  # nosec B603 B607 - ps with numeric PID
                                            ["ps", "-p", str(candidate_pid), "-o", "args="],
                                            capture_output=True,
                                            text=True,
                                            timeout=2.0,
                                        )
                                        if ps_result.returncode == 0:
                                            cmdline = ps_result.stdout.strip()
                                            # Verify it's actually the agent process
                                            # (contains session-id and matches expected CLI)
                                            # Check both provider name and "claude" (for cursor/windsurf/copilot)
                                            is_matched = agent.provider in cmdline.lower()
                                            if not is_matched and agent.provider in (
                                                "cursor",
                                                "windsurf",
                                                "copilot",
                                            ):
                                                is_matched = "claude" in cmdline.lower()

                                            if (
                                                f"session-id {agent.session_id}" in cmdline
                                                and is_matched
                                            ):
                                                if matched_pid is not None:
                                                    # Multiple matches - ambiguous
                                                    self._logger.error(
                                                        f"Ambiguous PID match: both {matched_pid} "
                                                        f"and {candidate_pid} match session "
                                                        f"{agent.session_id}"
                                                    )
                                                    matched_pid = None
                                                    break
                                                matched_pid = candidate_pid
                                    except (ValueError, subprocess.TimeoutExpired):
                                        continue
                                if matched_pid is not None:
                                    target_pid = matched_pid
                                    found_via = "pgrep_disambiguated"
                                    self._logger.info(
                                        f"Disambiguated PID via ps inspection: {target_pid}"
                                    )
                                else:
                                    self._logger.error(
                                        f"Could not disambiguate PIDs for session "
                                        f"{agent.session_id}: {pids}"
                                    )
                    except Exception as e:
                        self._logger.warning(f"pgrep fallback failed: {e}")

        if not target_pid:
            return {"success": False, "error": "No target PID found"}

        # Check if process is alive
        try:
            os.kill(target_pid, 0)
        except ProcessLookupError:
            self.remove(run_id, status="completed")
            return {
                "success": True,
                "message": f"Process {target_pid} already dead",
                "already_dead": True,
            }
        except PermissionError:
            return {"success": False, "error": f"No permission to signal PID {target_pid}"}

        # Close PTY if embedded mode
        if agent.master_fd is not None:
            try:
                os.close(agent.master_fd)
            except OSError:
                pass

        # Send signal
        sig = getattr(signal, f"SIG{signal_name}", signal.SIGTERM)
        try:
            os.kill(target_pid, sig)
        except ProcessLookupError:
            self.remove(run_id, status="completed")
            return {
                "success": True,
                "message": "Process died during signal",
                "already_dead": True,
            }

        # Wait for termination with optional SIGKILL escalation
        if signal_name == "TERM" and timeout > 0:
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    os.kill(target_pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    break
            else:
                # Still alive - escalate to SIGKILL
                try:
                    os.kill(target_pid, signal.SIGKILL)
                    self._logger.info(f"Escalated to SIGKILL for PID {target_pid}")
                except ProcessLookupError:
                    pass

        self.remove(run_id, status="killed")
        return {
            "success": True,
            "message": f"Sent SIG{signal_name} to PID {target_pid}",
            "pid": target_pid,
            "signal": signal_name,
            "found_via": found_via,
        }

    def get_by_session(self, session_id: str) -> RunningAgent | None:
        """
        Get a running agent by its child session ID.

        Args:
            session_id: The child session ID.

        Returns:
            The RunningAgent if found, None otherwise.
        """
        with self._lock:
            for agent in self._agents.values():
                if agent.session_id == session_id:
                    return agent
            return None

    def get_by_pid(self, pid: int) -> RunningAgent | None:
        """
        Get a running agent by its process ID.

        Args:
            pid: The process ID.

        Returns:
            The RunningAgent if found, None otherwise.
        """
        with self._lock:
            for agent in self._agents.values():
                if agent.pid == pid:
                    return agent
            return None

    def list_by_parent(self, parent_session_id: str) -> list[RunningAgent]:
        """
        List all running agents for a parent session.

        Args:
            parent_session_id: The parent session ID.

        Returns:
            List of running agents spawned by this parent.
        """
        with self._lock:
            return [
                agent
                for agent in self._agents.values()
                if agent.parent_session_id == parent_session_id
            ]

    def list_by_mode(self, mode: str) -> list[RunningAgent]:
        """
        List all running agents by execution mode.

        Args:
            mode: Execution mode (in_process, terminal, embedded, headless).

        Returns:
            List of running agents with this mode.
        """
        with self._lock:
            return [agent for agent in self._agents.values() if agent.mode == mode]

    def list_all(self) -> list[RunningAgent]:
        """
        List all running agents.

        Returns:
            List of all running agents (copy of current state).
        """
        with self._lock:
            return list(self._agents.values())

    def count(self) -> int:
        """
        Get the number of running agents.

        Returns:
            Count of running agents.
        """
        with self._lock:
            return len(self._agents)

    def count_by_parent(self, parent_session_id: str) -> int:
        """
        Count running agents for a parent session.

        Args:
            parent_session_id: The parent session ID.

        Returns:
            Count of running agents for this parent.
        """
        with self._lock:
            return sum(
                1 for agent in self._agents.values() if agent.parent_session_id == parent_session_id
            )

    def cleanup_by_pids(self, dead_pids: set[int]) -> list[RunningAgent]:
        """
        Remove agents whose PIDs are no longer running.

        This should be called periodically by a cleanup process that
        checks which PIDs are still alive.

        Args:
            dead_pids: Set of PIDs that are no longer running.

        Returns:
            List of agents that were removed.
        """
        removed: list[RunningAgent] = []
        with self._lock:
            for run_id, agent in list(self._agents.items()):
                if agent.pid and agent.pid in dead_pids:
                    self._agents.pop(run_id)
                    removed.append(agent)
                    self._logger.info(f"Cleaned up agent {run_id} with dead PID {agent.pid}")
        # Emit events outside lock for each removed agent
        for agent in removed:
            self._emit_event(
                "agent_completed",
                agent.run_id,
                {
                    "session_id": agent.session_id,
                    "parent_session_id": agent.parent_session_id,
                    "mode": agent.mode,
                    "provider": agent.provider,
                    "cleanup_reason": "dead_pid",
                },
            )
        return removed

    def cleanup_stale(self, max_age_seconds: float = 3600.0) -> list[RunningAgent]:
        """
        Remove agents that have been running longer than max_age.

        Args:
            max_age_seconds: Maximum age in seconds before cleanup (default: 1 hour).

        Returns:
            List of agents that were removed.
        """
        now = datetime.now(UTC)
        removed: list[RunningAgent] = []
        with self._lock:
            for run_id, agent in list(self._agents.items()):
                age = (now - agent.started_at).total_seconds()
                if age > max_age_seconds:
                    self._agents.pop(run_id)
                    removed.append(agent)
                    self._logger.info(f"Cleaned up stale agent {run_id} (age={age:.0f}s)")
        # Emit events outside lock for each removed agent
        for agent in removed:
            self._emit_event(
                "agent_timeout",
                agent.run_id,
                {
                    "session_id": agent.session_id,
                    "parent_session_id": agent.parent_session_id,
                    "mode": agent.mode,
                    "provider": agent.provider,
                    "cleanup_reason": "stale",
                },
            )
        return removed

    def clear(self) -> int:
        """
        Clear all running agents from the registry.

        Returns:
            Number of agents that were cleared.
        """
        with self._lock:
            count = len(self._agents)
            self._agents.clear()
            self._logger.info(f"Cleared {count} running agents from registry")
            return count


# Global singleton instance
_default_registry: RunningAgentRegistry | None = None
_registry_lock = threading.Lock()


def get_running_agent_registry() -> RunningAgentRegistry:
    """
    Get the global running agent registry singleton.

    Returns:
        The shared RunningAgentRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        with _registry_lock:
            if _default_registry is None:
                _default_registry = RunningAgentRegistry()
    return _default_registry
