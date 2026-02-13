"""
Query and management functions for agent runs.

Extracted from runner.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner

logger = logging.getLogger(__name__)


def get_run(runner: AgentRunner, run_id: str) -> Any | None:
    """Get an agent run by ID."""
    return runner._run_storage.get(run_id)


def get_run_id_by_session(runner: AgentRunner, session_id: str) -> str | None:
    """
    Get agent run_id by child session_id.

    Looks up the agent_runs table for a run with this child_session_id.

    Args:
        runner: The AgentRunner instance.
        session_id: The child session ID (UUID format).

    Returns:
        The run_id if found, None otherwise.
    """
    row = runner.db.fetchone(
        "SELECT id FROM agent_runs WHERE child_session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    )
    return row["id"] if row else None


def list_runs(
    runner: AgentRunner,
    parent_session_id: str,
    status: str | None = None,
    limit: int = 100,
) -> list[Any]:
    """List agent runs for a session."""
    return runner._run_storage.list_by_session(
        parent_session_id,
        status=status,  # type: ignore
        limit=limit,
    )


def cancel_run(runner: AgentRunner, run_id: str) -> bool:
    """Cancel a running agent."""
    run = runner._run_storage.get(run_id)
    if not run:
        return False
    if run.status != "running":
        return False

    runner._run_storage.cancel(run_id)

    # Also mark session as cancelled
    if run.child_session_id:
        runner._session_storage.update_status(run.child_session_id, "cancelled")

    runner.logger.info(f"Cancelled agent run {run_id}")

    # Remove from in-memory tracking
    runner._tracker.untrack(run_id)

    return True
