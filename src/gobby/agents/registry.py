"""
In-memory registry for tracking running agent processes.

This module provides thread-safe tracking of running agents that complements
the database storage. It tracks runtime information like PIDs and process handles
that shouldn't be persisted.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Event callback type - (event_type, run_id, data)
EventCallback = Callable[[str, str, dict[str, Any]], None]


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
