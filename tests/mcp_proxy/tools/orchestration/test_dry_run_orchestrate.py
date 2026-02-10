"""Tests for dry_run mode in orchestrate_ready_tasks.

Verifies that dry_run=True resolves tasks, checks capacity, builds prompts,
and returns the plan without spawning agents or creating worktrees.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.runner import AgentRunner
from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.task_orchestration import create_orchestration_registry
from gobby.storage.database import LocalDatabase
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.storage.worktrees import LocalWorktreeManager
from gobby.workflows.state_manager import WorkflowStateManager
from gobby.worktrees.git import WorktreeGitManager

pytestmark = [pytest.mark.unit]

PARENT_SESSION = "orch-dry-1"
PROJECT_ID = "test-dry-run-project"


def _make_task(
    task_id: str,
    title: str,
    parent_id: str = "PARENT",
    category: str | None = "code",
    description: str | None = None,
) -> Task:
    return Task(
        id=task_id,
        title=title,
        project_id=PROJECT_ID,
        status="open",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        category=category,
        description=description,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def db() -> LocalDatabase:
    from gobby.storage.migrations import run_migrations

    database = LocalDatabase(":memory:")
    run_migrations(database)
    return database


@pytest.fixture
def state_manager(db: LocalDatabase) -> WorkflowStateManager:
    return WorkflowStateManager(db)


@pytest.fixture
def mock_task_manager(db: LocalDatabase) -> MagicMock:
    m = MagicMock(spec=LocalTaskManager)
    m.db = db
    return m


@pytest.fixture
def mock_worktree_storage():
    return MagicMock(spec=LocalWorktreeManager)


@pytest.fixture
def mock_git_manager():
    m = MagicMock(spec=WorktreeGitManager)
    m.repo_path = "/repo"
    return m


@pytest.fixture
def mock_agent_runner():
    runner = MagicMock(spec=AgentRunner)
    runner.can_spawn.return_value = (True, None, 1)
    runner._child_session_manager = MagicMock()
    runner._child_session_manager.max_agent_depth = 3
    return runner


@pytest.fixture
def registry(
    mock_task_manager: MagicMock,
    mock_worktree_storage: MagicMock,
    mock_git_manager: MagicMock,
    mock_agent_runner: MagicMock,
) -> InternalToolRegistry:
    return create_orchestration_registry(
        task_manager=mock_task_manager,
        worktree_storage=mock_worktree_storage,
        git_manager=mock_git_manager,
        agent_runner=mock_agent_runner,
        project_id=PROJECT_ID,
    )


@pytest.fixture
def workflow_state(db: LocalDatabase, state_manager: WorkflowStateManager) -> None:
    """Pre-populate workflow state for the orchestrator session."""
    from gobby.workflows.definitions import WorkflowState

    now = datetime.now(UTC).isoformat()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (PROJECT_ID, "test-dry-run", now, now),
        )
        conn.execute(
            "INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (PARENT_SESSION, PROJECT_ID, "ext-dry-1", "machine-1", "claude", now, now),
        )

    initial_state = WorkflowState(
        session_id=PARENT_SESSION,
        workflow_name="auto-orchestrator",
        step="orchestrate",
        step_entered_at=datetime.now(UTC),
        variables={
            "spawned_agents": [],
            "completed_agents": [],
            "failed_agents": [],
        },
    )
    state_manager.save_state(initial_state)


class TestDryRunOrchestrateReadyTasks:
    """Test dry_run=True in orchestrate_ready_tasks."""

    @pytest.mark.asyncio
    async def test_dry_run_returns_plan_without_spawning(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """dry_run returns planned tasks with prompts but never spawns."""
        tool = registry.get_tool("orchestrate_ready_tasks")
        tasks = [
            _make_task("T1", "Implement auth", description="Add JWT auth"),
            _make_task("T2", "Add tests", category="test"),
        ]

        mock_worktree_storage.list_worktrees.return_value = []

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=tasks,
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
        ):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=3,
                dry_run=True,
            )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["planned_count"] == 2
        assert result["skipped_count"] == 0

        # Verify planned tasks contain expected fields
        planned = result["planned"]
        assert len(planned) == 2
        assert planned[0]["task_id"] == "T1"
        assert planned[0]["title"] == "Implement auth"
        assert planned[0]["category"] == "code"
        assert "JWT auth" in planned[0]["prompt"]
        assert planned[0]["provider"] == "gemini"  # default
        assert planned[0]["workflow"] == "auto-task"

        assert planned[1]["task_id"] == "T2"
        assert planned[1]["category"] == "test"

        # Verify NO spawning happened
        mock_agent_runner.prepare_run.assert_not_called()
        mock_git_manager.create_worktree.assert_not_called()
        mock_worktree_storage.create.assert_not_called()

        # Verify workflow state NOT modified (no spawned_agents added)
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["spawned_agents"]) == 0

    @pytest.mark.asyncio
    async def test_dry_run_respects_max_concurrent(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
    ) -> None:
        """dry_run correctly splits planned vs skipped by max_concurrent."""
        tool = registry.get_tool("orchestrate_ready_tasks")
        tasks = [_make_task(f"T{i}", f"Task {i}") for i in range(4)]

        mock_worktree_storage.list_worktrees.return_value = []

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=tasks,
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
        ):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=2,
                dry_run=True,
            )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["planned_count"] == 2
        assert result["skipped_count"] == 2
        assert result["max_concurrent"] == 2

        # Verify skipped tasks have reason
        for s in result["skipped"]:
            assert "max_concurrent" in s["reason"]

    @pytest.mark.asyncio
    async def test_dry_run_uses_effective_provider(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
    ) -> None:
        """dry_run resolves effective provider from coding_provider param."""
        tool = registry.get_tool("orchestrate_ready_tasks")
        tasks = [_make_task("T1", "Task 1")]

        mock_worktree_storage.list_worktrees.return_value = []

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=tasks,
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
        ):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                coding_provider="claude",
                coding_model="claude-opus-4-5",
                dry_run=True,
            )

        assert result["success"] is True
        assert result["effective_provider"] == "claude"
        assert result["effective_model"] == "claude-opus-4-5"
        assert result["planned"][0]["provider"] == "claude"
        assert result["planned"][0]["model"] == "claude-opus-4-5"

    @pytest.mark.asyncio
    async def test_dry_run_no_ready_tasks(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        workflow_state: None,
    ) -> None:
        """dry_run with no ready tasks returns empty plan."""
        tool = registry.get_tool("orchestrate_ready_tasks")

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=[],
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
        ):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                dry_run=True,
            )

        # No ready tasks = early return before dry_run check
        assert result["success"] is True
        assert result["spawned"] == []

    @pytest.mark.asyncio
    async def test_dry_run_releases_reserved_slots(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """dry_run releases reserved slots so subsequent real runs can use them."""
        tool = registry.get_tool("orchestrate_ready_tasks")
        tasks = [_make_task("T1", "Task 1")]

        mock_worktree_storage.list_worktrees.return_value = []

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=tasks,
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
        ):
            dry_result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                dry_run=True,
            )

        assert dry_result["success"] is True
        assert dry_result["dry_run"] is True

        # Verify reserved_slots were released by checking state
        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        reserved = state.variables.get("reserved_slots", 0)
        assert reserved == 0

    @pytest.mark.asyncio
    async def test_dry_run_prompt_contains_task_details(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
    ) -> None:
        """dry_run builds prompts that include title, description, and validation criteria."""
        tool = registry.get_tool("orchestrate_ready_tasks")

        task = _make_task(
            "T1",
            "Add user validation",
            description="Validate email format and password strength",
        )
        task.validation_criteria = "Must reject emails without @ symbol"

        mock_worktree_storage.list_worktrees.return_value = []

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=[task],
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
        ):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                dry_run=True,
            )

        prompt = result["planned"][0]["prompt"]
        assert "Add user validation" in prompt
        assert "Validate email format" in prompt
        assert "reject emails without @" in prompt
