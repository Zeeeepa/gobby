"""
Tests for worktree release during retry paths in process_completed_agents.

Verifies that validation-failed retries and crashed-agent retries release
the worktree so orchestrate_ready_tasks can reuse it instead of orphaning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.orchestration.review import register_reviewer
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.workflows.state_manager import WorkflowStateManager

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@dataclass
class FakeTask:
    """Minimal Task stand-in for testing."""

    id: str
    status: str
    validation_status: str | None = None
    validation_feedback: str | None = None
    validation_fail_count: int = 0
    closed_at: str | None = None
    closed_reason: str | None = None
    closed_commit_sha: str | None = None


@dataclass
class FakeWorktree:
    """Minimal Worktree stand-in."""

    id: str
    task_id: str | None = None
    agent_session_id: str | None = None


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    database = LocalDatabase(tmp_path / "test.db")
    run_migrations(database)
    database.execute(
        "INSERT INTO projects (id, name) VALUES (?, ?)",
        ("proj1", "test-project"),
    )
    yield database
    database.close()


@pytest.fixture
def state_manager(db) -> WorkflowStateManager:
    return WorkflowStateManager(db)


def _ensure_session(db, session_id: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO sessions (id, external_id, machine_id, source, project_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, session_id, "test-machine", "claude", "proj1"),
    )


def _insert_state(db, session_id: str, variables: dict[str, Any]) -> None:
    _ensure_session(db, session_id)
    db.execute(
        """
        INSERT INTO workflow_states (
            session_id, workflow_name, step, step_entered_at,
            step_action_count, total_action_count,
            observations, reflection_pending, context_injected,
            variables, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            "test_wf",
            "review",
            datetime.now(UTC).isoformat(),
            0,
            0,
            "[]",
            0,
            0,
            json.dumps(variables),
            datetime.now(UTC).isoformat(),
        ),
    )


def _make_registry(
    task_manager: MagicMock,
    worktree_storage: MagicMock,
    agent_runner: MagicMock,
    max_validation_retries: int = 3,
) -> InternalToolRegistry:
    """Register review tools and return the registry."""
    registry = InternalToolRegistry("test-review")
    register_reviewer(
        registry=registry,
        task_manager=task_manager,
        worktree_storage=worktree_storage,
        agent_runner=agent_runner,
        default_project_id="proj1",
        max_validation_retries=max_validation_retries,
    )
    return registry


class TestValidationRetryReleasesWorktree:
    """Validation-failed retry path releases worktree for reuse."""

    async def test_releases_worktree_on_validation_retry(self, db, state_manager) -> None:
        """When validation fails and retry count < max, worktree is released."""
        parent_sid = "orchestrator-1"
        task_id = "task-abc"
        wt_id = "wt-123"

        _insert_state(
            db,
            parent_sid,
            {
                "completed_agents": [{"task_id": task_id, "session_id": "agent-1"}],
                "failed_agents": [],
            },
        )

        task_manager = MagicMock()
        task_manager.db = db
        task_manager.get_task.return_value = FakeTask(
            id=task_id,
            status="closed",
            validation_status="invalid",
            validation_fail_count=1,
        )
        task_manager.reopen_task.return_value = None

        worktree_storage = MagicMock()
        worktree_storage.get_by_task.return_value = FakeWorktree(id=wt_id, task_id=task_id)

        agent_runner = MagicMock()

        registry = _make_registry(task_manager, worktree_storage, agent_runner)
        result = await registry.call(
            "process_completed_agents",
            {
                "parent_session_id": parent_sid,
                "spawn_reviews": False,
            },
        )

        assert result["success"] is True
        assert len(result["retries_scheduled"]) == 1
        assert result["retries_scheduled"][0]["worktree_id"] == wt_id

        # Verify worktree was released
        worktree_storage.get_by_task.assert_called_with(task_id)
        worktree_storage.release.assert_called_once_with(wt_id)

    async def test_retry_without_worktree(self, db, state_manager) -> None:
        """Retry works even if no worktree is linked to the task."""
        parent_sid = "orchestrator-1"
        task_id = "task-abc"

        _insert_state(
            db,
            parent_sid,
            {
                "completed_agents": [{"task_id": task_id, "session_id": "agent-1"}],
                "failed_agents": [],
            },
        )

        task_manager = MagicMock()
        task_manager.db = db
        task_manager.get_task.return_value = FakeTask(
            id=task_id,
            status="closed",
            validation_status="invalid",
            validation_fail_count=1,
        )
        task_manager.reopen_task.return_value = None

        worktree_storage = MagicMock()
        worktree_storage.get_by_task.return_value = None  # No worktree

        agent_runner = MagicMock()

        registry = _make_registry(task_manager, worktree_storage, agent_runner)
        result = await registry.call(
            "process_completed_agents",
            {
                "parent_session_id": parent_sid,
                "spawn_reviews": False,
            },
        )

        assert result["success"] is True
        assert len(result["retries_scheduled"]) == 1
        assert result["retries_scheduled"][0]["worktree_id"] is None
        worktree_storage.release.assert_not_called()

    async def test_escalates_when_max_retries_exceeded(self, db, state_manager) -> None:
        """When fail_count >= max_retries, escalates instead of retrying."""
        parent_sid = "orchestrator-1"
        task_id = "task-abc"

        _insert_state(
            db,
            parent_sid,
            {
                "completed_agents": [{"task_id": task_id, "session_id": "agent-1"}],
                "failed_agents": [],
            },
        )

        task_manager = MagicMock()
        task_manager.db = db
        task_manager.get_task.return_value = FakeTask(
            id=task_id,
            status="closed",
            validation_status="invalid",
            validation_fail_count=3,  # At max
        )

        worktree_storage = MagicMock()
        agent_runner = MagicMock()

        registry = _make_registry(
            task_manager, worktree_storage, agent_runner, max_validation_retries=3
        )
        result = await registry.call(
            "process_completed_agents",
            {
                "parent_session_id": parent_sid,
                "spawn_reviews": False,
            },
        )

        assert result["success"] is True
        assert len(result["escalated"]) == 1
        assert len(result["retries_scheduled"]) == 0
        # No worktree release on escalation
        worktree_storage.release.assert_not_called()


class TestCrashedAgentRetryReleasesWorktree:
    """Crashed-agent retry path releases worktree for reuse."""

    async def test_releases_worktree_on_crash_retry(self, db, state_manager) -> None:
        """When agent crashed and task is in_progress, worktree is released."""
        parent_sid = "orchestrator-1"
        task_id = "task-def"
        wt_id = "wt-456"

        _insert_state(
            db,
            parent_sid,
            {
                "completed_agents": [],
                "failed_agents": [
                    {
                        "task_id": task_id,
                        "session_id": "agent-2",
                        "failure_reason": "Agent exited without completing task",
                    }
                ],
            },
        )

        task_manager = MagicMock()
        task_manager.db = db
        task_manager.get_task.return_value = FakeTask(
            id=task_id,
            status="in_progress",
        )
        task_manager.update_task.return_value = None

        worktree_storage = MagicMock()
        worktree_storage.get_by_task.return_value = FakeWorktree(id=wt_id, task_id=task_id)

        agent_runner = MagicMock()

        registry = _make_registry(task_manager, worktree_storage, agent_runner)
        result = await registry.call(
            "process_completed_agents",
            {
                "parent_session_id": parent_sid,
                "spawn_reviews": False,
            },
        )

        assert result["success"] is True
        assert len(result["retries_scheduled"]) == 1
        assert result["retries_scheduled"][0]["worktree_id"] == wt_id

        # Verify worktree was released
        worktree_storage.get_by_task.assert_called_with(task_id)
        worktree_storage.release.assert_called_once_with(wt_id)

    async def test_crash_retry_without_worktree(self, db, state_manager) -> None:
        """Crash retry works even if no worktree is linked."""
        parent_sid = "orchestrator-1"
        task_id = "task-def"

        _insert_state(
            db,
            parent_sid,
            {
                "completed_agents": [],
                "failed_agents": [
                    {
                        "task_id": task_id,
                        "session_id": "agent-2",
                        "failure_reason": "Agent crashed unexpectedly",
                    }
                ],
            },
        )

        task_manager = MagicMock()
        task_manager.db = db
        task_manager.get_task.return_value = FakeTask(
            id=task_id,
            status="in_progress",
        )
        task_manager.update_task.return_value = None

        worktree_storage = MagicMock()
        worktree_storage.get_by_task.return_value = None

        agent_runner = MagicMock()

        registry = _make_registry(task_manager, worktree_storage, agent_runner)
        result = await registry.call(
            "process_completed_agents",
            {
                "parent_session_id": parent_sid,
                "spawn_reviews": False,
            },
        )

        assert result["success"] is True
        assert len(result["retries_scheduled"]) == 1
        worktree_storage.release.assert_not_called()

    async def test_non_retriable_failure_escalates(self, db, state_manager) -> None:
        """Non-retriable failures are escalated, not retried."""
        parent_sid = "orchestrator-1"
        task_id = "task-def"

        _insert_state(
            db,
            parent_sid,
            {
                "completed_agents": [],
                "failed_agents": [
                    {
                        "task_id": task_id,
                        "session_id": "agent-2",
                        "failure_reason": "Missing session_id in agent info",
                    }
                ],
            },
        )

        task_manager = MagicMock()
        task_manager.db = db

        worktree_storage = MagicMock()
        agent_runner = MagicMock()

        registry = _make_registry(task_manager, worktree_storage, agent_runner)
        result = await registry.call(
            "process_completed_agents",
            {
                "parent_session_id": parent_sid,
                "spawn_reviews": False,
            },
        )

        assert result["success"] is True
        assert len(result["escalated"]) == 1
        assert len(result["retries_scheduled"]) == 0
        worktree_storage.release.assert_not_called()
