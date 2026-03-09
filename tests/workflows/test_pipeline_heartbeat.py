"""Tests for PipelineHeartbeat cron handler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from gobby.agents.registry import RunningAgent, RunningAgentRegistry
from gobby.storage.pipelines import LocalPipelineExecutionManager
from gobby.workflows.pipeline_heartbeat import PipelineHeartbeat
from gobby.workflows.pipeline_state import ExecutionStatus

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

pytestmark = pytest.mark.unit

PROJECT_ID = "test-project"
SESSION_ID = "sess-test-001"


def _seed_db(db: "LocalDatabase") -> None:
    """Insert project + session rows to satisfy FK constraints."""
    db.execute(
        """INSERT OR IGNORE INTO projects (id, name, repo_path, created_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
        (PROJECT_ID, "test-project", "/tmp/test"),
    )
    db.execute(
        """INSERT OR IGNORE INTO sessions
           (id, external_id, machine_id, source, project_id, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        (SESSION_ID, "ext-1", "machine-1", "claude_code", PROJECT_ID, "active"),
    )


@pytest.fixture
def exec_manager(temp_db: LocalDatabase) -> LocalPipelineExecutionManager:
    _seed_db(temp_db)
    return LocalPipelineExecutionManager(temp_db, PROJECT_ID)


@pytest.fixture
def agent_registry() -> RunningAgentRegistry:
    return RunningAgentRegistry()


@pytest.fixture
def heartbeat(
    exec_manager: LocalPipelineExecutionManager,
    agent_registry: RunningAgentRegistry,
) -> PipelineHeartbeat:
    return PipelineHeartbeat(
        execution_manager=exec_manager,
        agent_registry=agent_registry,
        stall_threshold_seconds=60,
    )


def _create_stalled_execution(
    exec_manager: LocalPipelineExecutionManager,
    temp_db: LocalDatabase,
    stale_minutes: int = 5,
    session_id: str = SESSION_ID,
) -> str:
    """Create a running execution with an old updated_at timestamp."""
    exe = exec_manager.create_execution(
        pipeline_name="test-pipeline",
        session_id=session_id,
    )
    # Mark as running
    exec_manager.update_execution_status(exe.id, ExecutionStatus.RUNNING)
    # Backdate updated_at to make it stale
    stale_time = (datetime.now(UTC) - timedelta(minutes=stale_minutes)).isoformat()
    temp_db.execute(
        "UPDATE pipeline_executions SET updated_at = ? WHERE id = ?",
        (stale_time, exe.id),
    )
    return exe.id


def _add_alive_agent(
    agent_registry: RunningAgentRegistry,
    parent_session_id: str = SESSION_ID,
    run_id: str = "run-alive-001",
) -> None:
    """Register an alive agent for a parent session."""
    agent_registry.add(
        RunningAgent(
            run_id=run_id,
            session_id="sess-child-001",
            parent_session_id=parent_session_id,
            mode="terminal",
        )
    )


@pytest.mark.asyncio
async def test_stalled_no_agents_marks_failed(
    heartbeat: PipelineHeartbeat,
    exec_manager: LocalPipelineExecutionManager,
    temp_db: LocalDatabase,
) -> None:
    """Stalled execution with no alive agents → FAILED."""
    exe_id = _create_stalled_execution(exec_manager, temp_db)

    count = await heartbeat.check_stalled_executions()
    assert count == 1

    exe = exec_manager.get_execution(exe_id)
    assert exe is not None
    assert exe.status == ExecutionStatus.FAILED
    assert "stalled" in (exe.outputs_json or "").lower()


@pytest.mark.asyncio
async def test_stalled_with_alive_agents_touches_updated_at(
    heartbeat: PipelineHeartbeat,
    exec_manager: LocalPipelineExecutionManager,
    agent_registry: RunningAgentRegistry,
    temp_db: LocalDatabase,
) -> None:
    """Stalled execution with alive agents → updated_at refreshed, stays RUNNING."""
    exe_id = _create_stalled_execution(exec_manager, temp_db)
    _add_alive_agent(agent_registry)

    old_exe = exec_manager.get_execution(exe_id)
    assert old_exe is not None
    old_updated = old_exe.updated_at

    count = await heartbeat.check_stalled_executions()
    assert count == 1

    exe = exec_manager.get_execution(exe_id)
    assert exe is not None
    assert exe.status == ExecutionStatus.RUNNING
    assert exe.updated_at >= old_updated


@pytest.mark.asyncio
async def test_non_stalled_execution_untouched(
    heartbeat: PipelineHeartbeat,
    exec_manager: LocalPipelineExecutionManager,
) -> None:
    """Execution with recent updated_at is not flagged as stalled."""
    exe = exec_manager.create_execution(
        pipeline_name="test-pipeline",
        session_id=SESSION_ID,
    )
    exec_manager.update_execution_status(exe.id, ExecutionStatus.RUNNING)
    # Don't backdate — it's fresh

    count = await heartbeat.check_stalled_executions()
    assert count == 0

    refreshed = exec_manager.get_execution(exe.id)
    assert refreshed is not None
    assert refreshed.status == ExecutionStatus.RUNNING


@pytest.mark.asyncio
async def test_callable_cron_handler_interface(
    heartbeat: PipelineHeartbeat,
) -> None:
    """Heartbeat is callable with CronJob and returns a string."""
    mock_job = MagicMock()
    result = await heartbeat(mock_job)
    assert isinstance(result, str)
    assert "Heartbeat:" in result
