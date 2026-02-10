"""Parallel orchestrator integration test.

Tests the orchestrate_ready_tasks → poll_agent_status → cleanup flow
end-to-end with a real database (WorkflowStateManager) and mocked
external deps (agent_runner, git, worktrees).

Verifies:
- Capacity enforcement (max_concurrent)
- Workflow state persistence (spawned_agents list)
- Completion detection via task status
- Atomic list updates across tools
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.runner import AgentRunner
from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.task_orchestration import create_orchestration_registry
from gobby.storage.database import LocalDatabase
from gobby.storage.session_models import Session
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.storage.worktrees import LocalWorktreeManager, Worktree
from gobby.workflows.state_manager import WorkflowStateManager
from gobby.worktrees.git import GitOperationResult, WorktreeGitManager

pytestmark = [pytest.mark.unit]

PARENT_SESSION = "orch-parallel-1"
PROJECT_ID = "test-parallel-project"


def _make_task(task_id: str, title: str, parent_id: str = "PARENT") -> Task:
    return Task(
        id=task_id,
        title=title,
        project_id=PROJECT_ID,
        status="open",
        parent_task_id=parent_id,
        priority=2,
        task_type="task",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def db() -> LocalDatabase:
    """Real in-memory database with migrations for WorkflowStateManager."""
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
    m.db = db  # Real DB so WorkflowStateManager works
    return m


@pytest.fixture
def mock_worktree_storage() -> MagicMock:
    return MagicMock(spec=LocalWorktreeManager)


@pytest.fixture
def mock_git_manager() -> MagicMock:
    m = MagicMock(spec=WorktreeGitManager)
    m.repo_path = "/repo"
    return m


@pytest.fixture
def mock_agent_runner() -> MagicMock:
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
    """Pre-populate workflow state for the orchestrator session.

    Inserts project + session rows first to satisfy FK constraints on workflow_states.
    """
    from gobby.workflows.definitions import WorkflowState

    now = datetime.now(UTC).isoformat()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (PROJECT_ID, "test-parallel", now, now),
        )
        conn.execute(
            "INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (PARENT_SESSION, PROJECT_ID, "ext-1", "machine-1", "claude", now, now),
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


class TestParallelOrchestration:
    """Test orchestrate_ready_tasks → poll_agent_status flow."""

    @pytest.mark.asyncio
    async def test_spawn_respects_max_concurrent(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """3 tasks, max_concurrent=2: 2 spawned + 1 skipped."""
        tool = registry._tools["orchestrate_ready_tasks"]

        tasks = [_make_task(f"T{i}", f"Task {i}") for i in range(3)]

        # Track spawn count for unique session/run IDs
        spawn_count = {"n": 0}

        def make_prepare_result() -> MagicMock:
            spawn_count["n"] += 1
            n = spawn_count["n"]
            session = MagicMock(spec=Session)
            session.id = f"worker-sess-{n}"
            session.agent_depth = 1
            run = MagicMock()
            run.id = f"run-{n}"
            result = MagicMock()
            result.session = session
            result.run = run
            return result

        mock_agent_runner.prepare_run.side_effect = lambda *a, **kw: make_prepare_result()

        # Mock worktree creation
        wt_count = {"n": 0}

        def make_worktree(*args, **kwargs) -> Worktree:
            wt_count["n"] += 1
            n = wt_count["n"]
            return Worktree(
                id=f"wt-{n}",
                project_id=PROJECT_ID,
                branch_name=f"task/T{n - 1}",
                worktree_path=f"/tmp/wt-{n}",
                base_branch="main",
                task_id=f"T{n - 1}",
                agent_session_id=f"worker-sess-{n}",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
                merged_at=None,
            )

        mock_worktree_storage.create.side_effect = make_worktree
        mock_worktree_storage.get_by_task.return_value = None
        mock_worktree_storage.get_by_branch.return_value = None
        mock_worktree_storage.list_worktrees.return_value = []
        mock_git_manager.create_worktree.return_value = GitOperationResult(
            success=True, message="Created"
        )

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
            patch(
                "gobby.workflows.loader.WorkflowLoader.validate_workflow_for_agent_sync",
                return_value=(True, None),
            ),
            patch("gobby.agents.spawn.TerminalSpawner") as MockSpawner,
            patch("gobby.mcp_proxy.tools.worktrees._copy_project_json_to_worktree"),
            patch("gobby.mcp_proxy.tools.worktrees._install_provider_hooks"),
        ):
            MockSpawner.return_value.spawn_agent.return_value = MagicMock(
                success=True, pid=100, terminal_type="tmux"
            )

            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=2,
            )

        assert result["success"] is True
        assert result["spawned_count"] == 2
        assert result["skipped_count"] == 1

        # Verify skipped task and reason
        skipped = {s["task_id"]: s["reason"] for s in result["skipped"]}
        assert "T2" in skipped
        assert skipped["T2"] == "max_concurrent limit reached"

        # Verify workflow state persisted spawned_agents
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        spawned_agents = persisted.variables.get("spawned_agents", [])
        assert len(spawned_agents) == 2
        spawned_task_ids = {a["task_id"] for a in spawned_agents}
        assert spawned_task_ids == {"T0", "T1"}

    @pytest.mark.asyncio
    async def test_poll_detects_completion(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """poll_agent_status detects closed tasks and moves to completed_agents."""
        poll_tool = registry._tools["poll_agent_status"]

        # Pre-populate spawned_agents in workflow state
        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["spawned_agents"] = [
            {"session_id": "worker-1", "task_id": "T1", "worktree_id": "wt-1"},
            {"session_id": "worker-2", "task_id": "T2", "worktree_id": "wt-2"},
        ]
        state_manager.save_state(state)

        # T1 is closed (completed), T2 still in_progress
        closed_task = MagicMock()
        closed_task.status = "closed"
        closed_task.closed_at = "2024-01-01T01:00:00Z"
        closed_task.closed_reason = "completed"
        closed_task.closed_commit_sha = "abc123"

        open_task = MagicMock()
        open_task.status = "in_progress"

        def get_task(task_id: str) -> MagicMock:
            if task_id == "T1":
                return closed_task
            return open_task

        mock_task_manager.get_task.side_effect = get_task

        # Worker-2 is still running
        running_agent = MagicMock()
        running_agent.started_at = datetime.now(UTC)
        mock_agent_runner.get_running_agent.side_effect = (
            lambda sid: running_agent if sid == "worker-2" else None
        )

        # Worktrees still active
        mock_worktree_storage.get.return_value = MagicMock(agent_session_id="worker-2")

        result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert result["success"] is True
        assert len(result["newly_completed"]) == 1
        assert result["newly_completed"][0]["task_id"] == "T1"
        assert result["newly_completed"][0]["commit_sha"] == "abc123"
        assert len(result["still_running"]) == 1
        assert result["still_running"][0]["session_id"] == "worker-2"
        assert result["all_done"] is False

        # Verify workflow state updated atomically
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["spawned_agents"]) == 1  # Only worker-2
        assert persisted.variables["spawned_agents"][0]["session_id"] == "worker-2"
        assert len(persisted.variables["completed_agents"]) == 1
        assert persisted.variables["completed_agents"][0]["task_id"] == "T1"

    @pytest.mark.asyncio
    async def test_poll_all_done(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_agent_runner: MagicMock,
        mock_worktree_storage: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """poll_agent_status returns all_done=True when no agents running."""
        poll_tool = registry._tools["poll_agent_status"]

        # Single agent, already completed
        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["spawned_agents"] = [
            {"session_id": "worker-1", "task_id": "T1", "worktree_id": "wt-1"},
        ]
        state_manager.save_state(state)

        closed_task = MagicMock()
        closed_task.status = "closed"
        closed_task.closed_at = "2024-01-01T01:00:00Z"
        closed_task.closed_reason = "completed"
        closed_task.closed_commit_sha = "def456"

        mock_task_manager.get_task.return_value = closed_task
        mock_agent_runner.get_running_agent.return_value = None

        result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert result["success"] is True
        assert result["all_done"] is True
        assert len(result["newly_completed"]) == 1
        assert len(result["still_running"]) == 0

    @pytest.mark.asyncio
    async def test_poll_detects_failure(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_agent_runner: MagicMock,
        mock_worktree_storage: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """poll_agent_status detects crashed agents and moves to failed_agents."""
        poll_tool = registry._tools["poll_agent_status"]

        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["spawned_agents"] = [
            {"session_id": "worker-1", "task_id": "T1", "worktree_id": "wt-1"},
        ]
        state_manager.save_state(state)

        # Task still in_progress but agent not running (crashed)
        in_progress_task = MagicMock()
        in_progress_task.status = "in_progress"
        mock_task_manager.get_task.return_value = in_progress_task
        mock_agent_runner.get_running_agent.return_value = None

        # Worktree still claimed (agent didn't release)
        mock_worktree_storage.get.return_value = MagicMock(agent_session_id="worker-1")

        result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert result["success"] is True
        assert len(result["newly_failed"]) == 1
        assert "exited without completing" in result["newly_failed"][0]["failure_reason"]
        assert result["all_done"] is True

        # Verify failed_agents persisted
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["failed_agents"]) == 1
        assert len(persisted.variables["spawned_agents"]) == 0

    @pytest.mark.asyncio
    async def test_full_cycle_spawn_complete_respawn(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """Full cycle: spawn 2 → complete 1 → poll → respawn fills slot."""
        orchestrate_tool = registry._tools["orchestrate_ready_tasks"]
        poll_tool = registry._tools["poll_agent_status"]

        all_tasks = [_make_task(f"T{i}", f"Task {i}") for i in range(3)]

        # --- Phase 1: Initial spawn (2 of 3) ---
        spawn_count = {"n": 0}

        def make_prepare(*a: Any, **kw: Any) -> MagicMock:
            spawn_count["n"] += 1
            n = spawn_count["n"]
            session = MagicMock(spec=Session)
            session.id = f"worker-sess-{n}"
            session.agent_depth = 1
            run = MagicMock()
            run.id = f"run-{n}"
            result = MagicMock()
            result.session = session
            result.run = run
            return result

        mock_agent_runner.prepare_run.side_effect = make_prepare

        wt_n = {"n": 0}

        def make_wt(*a: Any, **kw: Any) -> Worktree:
            wt_n["n"] += 1
            n = wt_n["n"]
            return Worktree(
                id=f"wt-{n}",
                project_id=PROJECT_ID,
                branch_name=f"task/T{n - 1}",
                worktree_path=f"/tmp/wt-{n}",
                base_branch="main",
                task_id=kw.get("task_id", f"T{n - 1}"),
                agent_session_id=f"worker-sess-{n}",
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
                merged_at=None,
            )

        mock_worktree_storage.create.side_effect = make_wt
        mock_worktree_storage.get_by_task.return_value = None
        mock_worktree_storage.get_by_branch.return_value = None
        mock_worktree_storage.list_worktrees.return_value = []
        mock_git_manager.create_worktree.return_value = GitOperationResult(
            success=True, message="Created"
        )

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=all_tasks,
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
            patch(
                "gobby.workflows.loader.WorkflowLoader.validate_workflow_for_agent_sync",
                return_value=(True, None),
            ),
            patch("gobby.agents.spawn.TerminalSpawner") as MockSpawner,
            patch("gobby.mcp_proxy.tools.worktrees._copy_project_json_to_worktree"),
            patch("gobby.mcp_proxy.tools.worktrees._install_provider_hooks"),
        ):
            MockSpawner.return_value.spawn_agent.return_value = MagicMock(
                success=True, pid=200, terminal_type="tmux"
            )

            result1 = await orchestrate_tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=2,
            )

        assert result1["spawned_count"] == 2
        assert result1["skipped_count"] == 1

        # --- Phase 2: Complete T0, poll to detect ---
        def get_task_phase2(task_id: str) -> MagicMock:
            t = MagicMock()
            if task_id == "T0":
                t.status = "closed"
                t.closed_at = "2024-01-01T01:00:00Z"
                t.closed_reason = "completed"
                t.closed_commit_sha = "aaa111"
            else:
                t.status = "in_progress"
            return t

        mock_task_manager.get_task.side_effect = get_task_phase2

        running_agent = MagicMock()
        running_agent.started_at = datetime.now(UTC)
        mock_agent_runner.get_running_agent.side_effect = (
            lambda sid: running_agent if sid == "worker-sess-2" else None
        )
        mock_worktree_storage.get.return_value = MagicMock(agent_session_id="active")

        poll_result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert poll_result["success"] is True
        assert len(poll_result["newly_completed"]) == 1
        assert poll_result["newly_completed"][0]["task_id"] == "T0"
        assert len(poll_result["still_running"]) == 1
        assert poll_result["all_done"] is False

        # Verify state: 1 spawned, 1 completed
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["spawned_agents"]) == 1
        assert len(persisted.variables["completed_agents"]) == 1

        # --- Phase 3: Respawn fills the freed slot ---
        # Only T2 is left (T0 done, T1 still running)
        remaining_tasks = [all_tasks[2]]  # T2

        with (
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
                return_value=remaining_tasks,
            ),
            patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"),
            patch(
                "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                return_value=PROJECT_ID,
            ),
            patch(
                "gobby.workflows.loader.WorkflowLoader.validate_workflow_for_agent_sync",
                return_value=(True, None),
            ),
            patch("gobby.agents.spawn.TerminalSpawner") as MockSpawner2,
            patch("gobby.mcp_proxy.tools.worktrees._copy_project_json_to_worktree"),
            patch("gobby.mcp_proxy.tools.worktrees._install_provider_hooks"),
        ):
            MockSpawner2.return_value.spawn_agent.return_value = MagicMock(
                success=True, pid=300, terminal_type="tmux"
            )

            result3 = await orchestrate_tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=2,
            )

        assert result3["success"] is True
        assert result3["spawned_count"] == 1  # Filled the freed slot

        # Final state: 2 spawned (worker-2 + worker-3), 1 completed
        final = state_manager.get_state(PARENT_SESSION)
        assert final is not None
        assert len(final.variables["spawned_agents"]) == 2
        assert len(final.variables["completed_agents"]) == 1
