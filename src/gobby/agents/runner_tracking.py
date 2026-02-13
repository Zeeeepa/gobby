"""
In-memory tracking of running agents.

Extracted from runner.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
import threading

from gobby.agents.registry import RunningAgent

logger = logging.getLogger(__name__)


class RunTracker:
    """Thread-safe in-memory tracker for running agents.

    Maintains a dict of RunningAgent instances keyed by run_id,
    protected by a threading lock.
    """

    def __init__(self) -> None:
        self._running_agents: dict[str, RunningAgent] = {}
        self._lock = threading.Lock()

    def track(
        self,
        run_id: str,
        parent_session_id: str | None,
        child_session_id: str,
        provider: str,
        prompt: str,
        mode: str = "in_process",
        workflow_name: str | None = None,
        model: str | None = None,
        worktree_id: str | None = None,
        pid: int | None = None,
        terminal_type: str | None = None,
        master_fd: int | None = None,
    ) -> RunningAgent:
        """
        Add an agent to the in-memory running agents dict.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID.
            parent_session_id: Session that spawned this agent.
            child_session_id: Child session created for this agent.
            provider: LLM provider.
            prompt: The task prompt (not stored, kept for API compatibility).
            mode: Execution mode.
            workflow_name: Workflow being executed.
            model: Model override (not stored, kept for API compatibility).
            worktree_id: Worktree being used.
            pid: Process ID for terminal/headless mode.
            terminal_type: Terminal type for terminal mode.
            master_fd: PTY master file descriptor for embedded mode.

        Returns:
            The created RunningAgent instance.
        """
        # Note: The registry's RunningAgent uses 'session_id' for child session
        # and doesn't store prompt/model (those are in the database AgentRun record)
        _ = prompt  # Kept for API compatibility, stored in AgentRun
        _ = model  # Kept for API compatibility, stored in AgentRun
        running_agent = RunningAgent(
            run_id=run_id,
            session_id=child_session_id,
            parent_session_id=parent_session_id if parent_session_id else "",
            mode=mode,
            provider=provider,
            workflow_name=workflow_name,
            worktree_id=worktree_id,
            pid=pid,
            terminal_type=terminal_type,
            master_fd=master_fd,
        )

        with self._lock:
            self._running_agents[run_id] = running_agent

        logger.debug(f"Tracking running agent {run_id} (mode={mode})")
        return running_agent

    def untrack(self, run_id: str) -> RunningAgent | None:
        """
        Remove an agent from the in-memory running agents dict.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID to remove.

        Returns:
            The removed RunningAgent, or None if not found.
        """
        with self._lock:
            agent = self._running_agents.pop(run_id, None)

        if agent:
            logger.debug(f"Untracked running agent {run_id}")
        return agent

    def update(
        self,
        run_id: str,
        turns_used: int | None = None,
        tool_calls_count: int | None = None,
    ) -> RunningAgent | None:
        """
        Update in-memory state for a running agent.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID.
            turns_used: Updated turns count.
            tool_calls_count: Updated tool calls count.

        Returns:
            The RunningAgent if found, None otherwise.
        """
        from datetime import UTC, datetime

        with self._lock:
            agent = self._running_agents.get(run_id)
            if agent is not None:
                if turns_used is not None:
                    agent.turns_used = turns_used
                if tool_calls_count is not None:
                    agent.tool_calls_count = tool_calls_count
                agent.last_activity = datetime.now(UTC)

        return agent

    def get(self, run_id: str) -> RunningAgent | None:
        """
        Get a running agent by ID.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID.

        Returns:
            The RunningAgent if found and running, None otherwise.
        """
        with self._lock:
            return self._running_agents.get(run_id)

    def get_all(
        self,
        parent_session_id: str | None = None,
    ) -> list[RunningAgent]:
        """
        Get all running agents, optionally filtered by parent session.

        Thread-safe operation using a lock.

        Args:
            parent_session_id: Optional filter by parent session.

        Returns:
            List of running agents.
        """
        with self._lock:
            agents = list(self._running_agents.values())

        if parent_session_id:
            agents = [a for a in agents if a.parent_session_id == parent_session_id]

        return agents

    def count(self) -> int:
        """
        Get count of running agents.

        Thread-safe operation using a lock.

        Returns:
            Number of running agents.
        """
        with self._lock:
            return len(self._running_agents)

    def is_running(self, run_id: str) -> bool:
        """
        Check if an agent is currently running.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID.

        Returns:
            True if the agent is in the running dict.
        """
        with self._lock:
            return run_id in self._running_agents
