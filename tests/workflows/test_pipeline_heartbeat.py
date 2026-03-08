"""Tests for PipelineHeartbeat cron handler."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.agents.registry import RunningAgent, RunningAgentRegistry
from gobby.events.completion_registry import CompletionEventRegistry
from gobby.storage.agents import LocalAgentRunManager
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
def agent_run_manager(temp_db: LocalDatabase) -> LocalAgentRunManager:
    _seed_db(temp_db)
    return LocalAgentRunManager(temp_db)


@pytest.fixture
def completion_registry(temp_db: LocalDatabase) -> CompletionEventRegistry:
    return CompletionEventRegistry(
        pipeline_rerun_callback=AsyncMock(),
        db=temp_db,
    )


@pytest.fixture
def heartbeat(
    exec_manager: LocalPipelineExecutionManager,
    completion_registry: CompletionEventRegistry,
    agent_registry: RunningAgentRegistry,
    agent_run_manager: LocalAgentRunManager,
    temp_db: LocalDatabase,
) -> PipelineHeartbeat:
    return PipelineHeartbeat(
        execution_manager=exec_manager,
        completion_registry=completion_registry,
        agent_registry=agent_registry,
        agent_run_manager=agent_run_manager,
        db=temp_db,
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
async def test_stalled_no_agents_no_continuations_marks_failed(
    heartbeat: PipelineHeartbeat,
    exec_manager: LocalPipelineExecutionManager,
    temp_db: LocalDatabase,
) -> None:
    """Stalled execution with no alive agents and no continuations → FAILED."""
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
async def test_stalled_dead_agents_with_continuation_fires_it(
    heartbeat: PipelineHeartbeat,
    exec_manager: LocalPipelineExecutionManager,
    completion_registry: CompletionEventRegistry,
    temp_db: LocalDatabase,
) -> None:
    """Stalled execution + dead agents + orphaned continuation → continuation fired."""
    exe_id = _create_stalled_execution(exec_manager, temp_db)

    # Register a continuation in DB for this execution
    continuation_config = {
        "execution_id": exe_id,
        "pipeline_name": "test-pipeline",
        "inputs": {},
    }
    temp_db.execute(
        "INSERT OR REPLACE INTO pipeline_continuations (run_id, config_json) VALUES (?, ?)",
        ("run-dead-001", json.dumps(continuation_config)),
    )

    count = await heartbeat.check_stalled_executions()
    assert count == 1

    # Verify continuation callback was invoked
    assert completion_registry._pipeline_rerun_callback is not None
    completion_registry._pipeline_rerun_callback.assert_called_once()

    # Verify continuation was cleaned up from DB
    row = temp_db.fetchone(
        "SELECT * FROM pipeline_continuations WHERE run_id = ?",
        ("run-dead-001",),
    )
    assert row is None


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
async def test_orphaned_continuation_for_completed_agent_fired(
    heartbeat: PipelineHeartbeat,
    completion_registry: CompletionEventRegistry,
    agent_run_manager: LocalAgentRunManager,
    temp_db: LocalDatabase,
) -> None:
    """Orphaned continuation for a completed agent run → fired and cleaned up."""
    # Create an agent run that completed
    agent_run = agent_run_manager.create(
        parent_session_id=SESSION_ID,
        provider="claude",
        prompt="do something",
    )
    # Mark it as success
    agent_run_manager.complete(agent_run.id, result="done")

    # Add a continuation that should have been fired
    continuation_config = {
        "pipeline_name": "test-pipeline",
        "inputs": {},
    }
    temp_db.execute(
        "INSERT OR REPLACE INTO pipeline_continuations (run_id, config_json) VALUES (?, ?)",
        (agent_run.id, json.dumps(continuation_config)),
    )

    count = await heartbeat.check_orphaned_continuations()
    assert count == 1

    # Verify callback was invoked
    completion_registry._pipeline_rerun_callback.assert_called_once()

    # Verify cleanup
    row = temp_db.fetchone(
        "SELECT * FROM pipeline_continuations WHERE run_id = ?",
        (agent_run.id,),
    )
    assert row is None


@pytest.mark.asyncio
async def test_orphaned_continuation_for_running_agent_skipped(
    heartbeat: PipelineHeartbeat,
    completion_registry: CompletionEventRegistry,
    agent_registry: RunningAgentRegistry,
    temp_db: LocalDatabase,
) -> None:
    """Continuation for still-running agent → not fired."""
    run_id = "run-still-going"
    _add_alive_agent(agent_registry, run_id=run_id)

    continuation_config = {
        "pipeline_name": "test-pipeline",
        "inputs": {},
    }
    temp_db.execute(
        "INSERT OR REPLACE INTO pipeline_continuations (run_id, config_json) VALUES (?, ?)",
        (run_id, json.dumps(continuation_config)),
    )

    count = await heartbeat.check_orphaned_continuations()
    assert count == 0

    completion_registry._pipeline_rerun_callback.assert_not_called()


@pytest.mark.asyncio
async def test_callable_cron_handler_interface(
    heartbeat: PipelineHeartbeat,
) -> None:
    """Heartbeat is callable with CronJob and returns a string."""
    mock_job = MagicMock()
    result = await heartbeat(mock_job)
    assert isinstance(result, str)
    assert "Heartbeat:" in result
