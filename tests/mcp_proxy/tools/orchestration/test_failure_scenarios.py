"""Failure scenario tests for orchestration tools.

Tests edge cases and error handling:
- Worker crashes (agent exits without closing task)
- Worktree creation fails mid-spawn
- Merge conflict during cleanup
- Wait timeout with retry exhaustion
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
from gobby.storage.session_models import Session
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.storage.worktrees import LocalWorktreeManager, Worktree
from gobby.workflows.state_manager import WorkflowStateManager
from gobby.worktrees.git import GitOperationResult, WorktreeGitManager

pytestmark = [pytest.mark.unit]

PARENT_SESSION = "orch-fail-1"
PROJECT_ID = "test-failure-project"


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


# ── Fixtures ──────────────────────────────────────────────────────────


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
            (PROJECT_ID, "test-failure", now, now),
        )
        conn.execute(
            "INSERT INTO sessions (id, project_id, external_id, machine_id, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (PARENT_SESSION, PROJECT_ID, "ext-fail-1", "machine-1", "claude", now, now),
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
            "reviewed_agents": [],
        },
    )
    state_manager.save_state(initial_state)


def _prepare_result(n: int) -> MagicMock:
    """Create a mock prepare_run result for agent spawning."""
    session = MagicMock(spec=Session)
    session.id = f"worker-sess-{n}"
    session.agent_depth = 1
    run = MagicMock()
    run.id = f"run-{n}"
    result = MagicMock()
    result.session = session
    result.run = run
    return result


# ── 1. Worker crash scenarios ─────────────────────────────────────────


class TestWorkerCrash:
    """Test detection of crashed/failed workers via poll_agent_status."""

    @pytest.mark.asyncio
    async def test_multiple_workers_mixed_crash_and_complete(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_agent_runner: MagicMock,
        mock_worktree_storage: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """3 workers: 1 completes, 1 crashes, 1 still running."""
        poll_tool = registry._tools["poll_agent_status"]

        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["spawned_agents"] = [
            {"session_id": "w1", "task_id": "T1", "worktree_id": "wt-1"},
            {"session_id": "w2", "task_id": "T2", "worktree_id": "wt-2"},
            {"session_id": "w3", "task_id": "T3", "worktree_id": "wt-3"},
        ]
        state_manager.save_state(state)

        def get_task(task_id: str) -> MagicMock:
            t = MagicMock()
            if task_id == "T1":
                t.status = "closed"
                t.closed_at = "2024-01-01T01:00:00Z"
                t.closed_reason = "completed"
                t.closed_commit_sha = "abc123"
            else:
                t.status = "in_progress"
            return t

        mock_task_manager.get_task.side_effect = get_task

        running_agent = MagicMock()
        running_agent.started_at = datetime.now(UTC)
        mock_agent_runner.get_running_agent.side_effect = (
            lambda sid: running_agent if sid == "w3" else None
        )

        mock_worktree_storage.get.return_value = MagicMock(agent_session_id="active")

        result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert result["success"] is True
        assert len(result["newly_completed"]) == 1
        assert result["newly_completed"][0]["task_id"] == "T1"
        assert len(result["newly_failed"]) == 1
        assert result["newly_failed"][0]["task_id"] == "T2"
        assert "exited without completing" in result["newly_failed"][0]["failure_reason"]
        assert len(result["still_running"]) == 1
        assert result["still_running"][0]["session_id"] == "w3"
        assert result["all_done"] is False

        # Verify state persisted correctly
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["spawned_agents"]) == 1
        assert len(persisted.variables["completed_agents"]) == 1
        assert len(persisted.variables["failed_agents"]) == 1

    @pytest.mark.asyncio
    async def test_worker_crash_task_still_open(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_agent_runner: MagicMock,
        mock_worktree_storage: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """Agent exits before even starting the task (task remains open)."""
        poll_tool = registry._tools["poll_agent_status"]

        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["spawned_agents"] = [
            {"session_id": "w1", "task_id": "T1", "worktree_id": "wt-1"},
        ]
        state_manager.save_state(state)

        open_task = MagicMock()
        open_task.status = "open"
        mock_task_manager.get_task.return_value = open_task
        mock_agent_runner.get_running_agent.return_value = None
        mock_worktree_storage.get.return_value = MagicMock(agent_session_id="w1")

        result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert result["success"] is True
        assert len(result["newly_failed"]) == 1
        assert "not running and task not started" in result["newly_failed"][0]["failure_reason"]
        assert result["all_done"] is True

    @pytest.mark.asyncio
    async def test_worker_missing_session_id(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_agent_runner: MagicMock,
        mock_worktree_storage: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """Corrupted agent info with missing session_id is detected as failure."""
        poll_tool = registry._tools["poll_agent_status"]

        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["spawned_agents"] = [
            {"task_id": "T1", "worktree_id": "wt-1"},  # Missing session_id
        ]
        state_manager.save_state(state)

        result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert result["success"] is True
        assert len(result["newly_failed"]) == 1
        assert "Missing session_id" in result["newly_failed"][0]["failure_reason"]

    @pytest.mark.asyncio
    async def test_worker_released_worktree_without_closing_task(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_agent_runner: MagicMock,
        mock_worktree_storage: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """Agent released its worktree but never closed the task."""
        poll_tool = registry._tools["poll_agent_status"]

        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["spawned_agents"] = [
            {"session_id": "w1", "task_id": "T1", "worktree_id": "wt-1"},
        ]
        state_manager.save_state(state)

        in_progress_task = MagicMock()
        in_progress_task.status = "in_progress"
        mock_task_manager.get_task.return_value = in_progress_task

        # Worktree exists but agent_session_id is None (released)
        released_worktree = MagicMock()
        released_worktree.agent_session_id = None
        mock_worktree_storage.get.return_value = released_worktree

        result = await poll_tool.func(parent_session_id=PARENT_SESSION)

        assert result["success"] is True
        assert len(result["newly_failed"]) == 1
        assert "released worktree without closing" in result["newly_failed"][0]["failure_reason"]


# ── 2. Worktree creation failure ──────────────────────────────────────


class TestWorktreeCreationFailure:
    """Test orchestrate_ready_tasks when worktree creation fails."""

    @pytest.mark.asyncio
    async def test_git_worktree_creation_fails(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
    ) -> None:
        """Git worktree creation returns failure — task is skipped gracefully."""
        tool = registry._tools["orchestrate_ready_tasks"]
        tasks = [_make_task("T1", "Task 1")]

        mock_worktree_storage.get_by_task.return_value = None
        mock_worktree_storage.get_by_branch.return_value = None
        mock_worktree_storage.list_worktrees.return_value = []
        mock_git_manager.create_worktree.return_value = GitOperationResult(
            success=False,
            message="fatal: worktree path already exists",
            error="fatal: worktree path already exists",
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
        ):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=3,
            )

        assert result["success"] is True
        assert result["spawned_count"] == 0
        assert result["skipped_count"] == 1
        assert "worktree" in result["skipped"][0]["reason"].lower()

    @pytest.mark.asyncio
    async def test_project_json_copy_fails_cleans_up_worktree(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
    ) -> None:
        """If _copy_project_json_to_worktree fails, worktree is cleaned up."""
        tool = registry._tools["orchestrate_ready_tasks"]
        tasks = [_make_task("T1", "Task 1")]

        mock_worktree_storage.get_by_task.return_value = None
        mock_worktree_storage.get_by_branch.return_value = None
        mock_worktree_storage.list_worktrees.return_value = []
        mock_git_manager.create_worktree.return_value = GitOperationResult(
            success=True, message="Created"
        )

        wt = Worktree(
            id="wt-1",
            project_id=PROJECT_ID,
            branch_name="task/T1",
            worktree_path="/tmp/wt-1",
            base_branch="main",
            task_id="T1",
            agent_session_id=None,
            status="active",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            merged_at=None,
        )
        mock_worktree_storage.create.return_value = wt

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
            patch(
                "gobby.mcp_proxy.tools.worktrees._copy_project_json_to_worktree",
                side_effect=OSError("Permission denied"),
            ),
            patch("gobby.mcp_proxy.tools.worktrees._install_provider_hooks"),
        ):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=3,
            )

        assert result["success"] is True
        assert result["spawned_count"] == 0
        assert result["skipped_count"] == 1
        assert "initialization failed" in result["skipped"][0]["reason"].lower()

        # Verify cleanup was called
        mock_worktree_storage.delete.assert_called_once_with("wt-1")
        mock_git_manager.delete_worktree.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_failure_releases_worktree(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
    ) -> None:
        """If agent spawn fails after worktree is created, worktree is released and cleaned up."""
        tool = registry._tools["orchestrate_ready_tasks"]
        tasks = [_make_task("T1", "Task 1")]

        mock_worktree_storage.get_by_task.return_value = None
        mock_worktree_storage.get_by_branch.return_value = None
        mock_worktree_storage.list_worktrees.return_value = []
        mock_git_manager.create_worktree.return_value = GitOperationResult(
            success=True, message="Created"
        )

        wt = Worktree(
            id="wt-1",
            project_id=PROJECT_ID,
            branch_name="task/T1",
            worktree_path="/tmp/wt-1",
            base_branch="main",
            task_id="T1",
            agent_session_id=None,
            status="active",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            merged_at=None,
        )
        mock_worktree_storage.create.return_value = wt

        mock_agent_runner.prepare_run.return_value = _prepare_result(1)

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
            patch("gobby.mcp_proxy.tools.worktrees._copy_project_json_to_worktree"),
            patch("gobby.mcp_proxy.tools.worktrees._install_provider_hooks"),
            patch("gobby.agents.spawn.TerminalSpawner") as MockSpawner,
        ):
            MockSpawner.return_value.spawn_agent.return_value = MagicMock(
                success=False, error="tmux session not found", pid=None
            )

            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                max_concurrent=3,
            )

        assert result["success"] is True
        assert result["spawned_count"] == 0
        assert result["skipped_count"] == 1
        # The error message from the spawner is used as the skip reason
        assert "tmux" in result["skipped"][0]["reason"].lower() or "spawn" in result["skipped"][0]["reason"].lower()

        # Verify worktree cleanup
        mock_worktree_storage.release.assert_called_once_with("wt-1")
        mock_worktree_storage.delete.assert_called_once_with("wt-1")

    @pytest.mark.asyncio
    async def test_partial_spawn_some_succeed_some_fail(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """2 tasks: first succeeds, second fails during spawn. State reflects partial success."""
        tool = registry._tools["orchestrate_ready_tasks"]
        tasks = [_make_task("T1", "Task 1"), _make_task("T2", "Task 2")]

        mock_worktree_storage.get_by_task.return_value = None
        mock_worktree_storage.get_by_branch.return_value = None
        mock_worktree_storage.list_worktrees.return_value = []

        wt_count = {"n": 0}

        def make_worktree(*args: Any, **kwargs: Any) -> Worktree:
            wt_count["n"] += 1
            n = wt_count["n"]
            return Worktree(
                id=f"wt-{n}",
                project_id=PROJECT_ID,
                branch_name=f"task/T{n}",
                worktree_path=f"/tmp/wt-{n}",
                base_branch="main",
                task_id=kwargs.get("task_id", f"T{n}"),
                agent_session_id=None,
                status="active",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
                merged_at=None,
            )

        mock_worktree_storage.create.side_effect = make_worktree

        # First git worktree succeeds, second fails
        mock_git_manager.create_worktree.side_effect = [
            GitOperationResult(success=True, message="Created"),
            GitOperationResult(
                success=False,
                message="disk full",
                error="No space left on device",
            ),
        ]

        spawn_count = {"n": 0}

        def make_prepare(*a: Any, **kw: Any) -> MagicMock:
            spawn_count["n"] += 1
            return _prepare_result(spawn_count["n"])

        mock_agent_runner.prepare_run.side_effect = make_prepare

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
                max_concurrent=3,
            )

        assert result["success"] is True
        assert result["spawned_count"] == 1
        assert result["skipped_count"] == 1
        assert result["spawned"][0]["task_id"] == "T1"
        assert "worktree" in result["skipped"][0]["reason"].lower()

        # Verify state has 1 spawned agent
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["spawned_agents"]) == 1


# ── 3. Merge conflict during cleanup ─────────────────────────────────


class TestMergeConflict:
    """Test cleanup_reviewed_worktrees when merge conflicts occur."""

    @pytest.mark.asyncio
    async def test_merge_conflict_skips_worktree(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """Merge conflict during cleanup: agent is reported as failed, not cleaned."""
        cleanup_tool = registry._tools["cleanup_reviewed_worktrees"]

        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["reviewed_agents"] = [
            {
                "session_id": "w1",
                "task_id": "T1",
                "worktree_id": "wt-1",
                "branch_name": "task/T1",
            },
        ]
        state_manager.save_state(state)

        # Worktree exists with base_branch set
        wt = MagicMock()
        wt.worktree_path = "/tmp/wt-1"
        wt.branch_name = "task/T1"
        wt.base_branch = "dev"
        mock_worktree_storage.get.return_value = wt

        # Simulate merge conflict
        conflict_result = MagicMock()
        conflict_result.returncode = 1
        conflict_result.stdout = "CONFLICT (content): Merge conflict in src/foo.py"
        conflict_result.stderr = ""

        abort_result = MagicMock()
        abort_result.returncode = 0

        call_count = {"n": 0}

        def mock_run_git(args: list[str], **kwargs: Any) -> MagicMock:
            call_count["n"] += 1
            cmd = args[0] if args else ""
            if cmd == "fetch":
                r = MagicMock()
                r.returncode = 0
                return r
            if cmd == "checkout":
                r = MagicMock()
                r.returncode = 0
                return r
            if cmd == "pull":
                r = MagicMock()
                r.returncode = 0
                return r
            if cmd == "merge":
                if args[-1:] == ["--abort"]:
                    return abort_result
                return conflict_result
            r = MagicMock()
            r.returncode = 0
            return r

        mock_git_manager._run_git.side_effect = mock_run_git

        result = await cleanup_tool.func(
            parent_session_id=PARENT_SESSION,
            merge_to_base=True,
        )

        assert result["success"] is True
        assert len(result["merged"]) == 0
        assert len(result["failed"]) == 1
        assert "conflict" in result["failed"][0]["failure_reason"].lower()

        # Verify reviewed_agents NOT cleared (merge failed, agent still needs attention)
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["reviewed_agents"]) == 1

    @pytest.mark.asyncio
    async def test_merge_conflict_one_of_two(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        workflow_state: None,
        state_manager: WorkflowStateManager,
    ) -> None:
        """2 reviewed agents: one merges OK, one has conflict. Partial cleanup."""
        cleanup_tool = registry._tools["cleanup_reviewed_worktrees"]

        state = state_manager.get_state(PARENT_SESSION)
        assert state is not None
        state.variables["reviewed_agents"] = [
            {
                "session_id": "w1",
                "task_id": "T1",
                "worktree_id": "wt-1",
                "branch_name": "task/T1",
            },
            {
                "session_id": "w2",
                "task_id": "T2",
                "worktree_id": "wt-2",
                "branch_name": "task/T2",
            },
        ]
        state_manager.save_state(state)

        def get_worktree(wt_id: str) -> MagicMock:
            wt = MagicMock()
            wt.worktree_path = f"/tmp/{wt_id}"
            wt.branch_name = f"task/T{wt_id[-1]}"
            wt.base_branch = "dev"
            return wt

        mock_worktree_storage.get.side_effect = get_worktree

        merge_call_count = {"n": 0}

        def mock_run_git(args: list[str], **kwargs: Any) -> MagicMock:
            cmd = args[0] if args else ""
            r = MagicMock()

            if cmd in ("fetch", "checkout", "pull", "rev-parse", "push"):
                r.returncode = 0
                r.stdout = "abc123" if cmd == "rev-parse" else ""
                r.stderr = ""
                return r

            if cmd == "merge":
                if "--abort" in args:
                    r.returncode = 0
                    return r
                merge_call_count["n"] += 1
                if merge_call_count["n"] == 1:
                    # First merge succeeds
                    r.returncode = 0
                    r.stdout = ""
                    r.stderr = ""
                else:
                    # Second merge conflicts
                    r.returncode = 1
                    r.stdout = "CONFLICT (content): Merge conflict"
                    r.stderr = ""
                return r

            r.returncode = 0
            return r

        mock_git_manager._run_git.side_effect = mock_run_git

        delete_result = MagicMock()
        delete_result.success = True
        delete_result.message = "Deleted"
        mock_git_manager.delete_worktree.return_value = delete_result

        result = await cleanup_tool.func(
            parent_session_id=PARENT_SESSION,
            merge_to_base=True,
            delete_worktrees=True,
        )

        assert result["success"] is True
        assert len(result["merged"]) == 1
        assert result["merged"][0]["task_id"] == "T1"
        assert len(result["failed"]) == 1
        assert result["failed"][0]["task_id"] == "T2"

        # Only w1 should be cleaned from reviewed_agents
        persisted = state_manager.get_state(PARENT_SESSION)
        assert persisted is not None
        assert len(persisted.variables["reviewed_agents"]) == 1
        assert persisted.variables["reviewed_agents"][0]["worktree_id"] == "wt-2"


# ── 4. Wait timeout with retry exhaustion ─────────────────────────────


class TestWaitTimeout:
    """Test wait_for_task timeout and retry behavior."""

    @pytest.mark.asyncio
    async def test_wait_timeout_returns_timed_out(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
    ) -> None:
        """wait_for_task returns timed_out=True when timeout expires."""
        wait_tool = registry._tools["wait_for_task"]

        in_progress_task = MagicMock()
        in_progress_task.id = "T1"
        in_progress_task.seq_num = 1
        in_progress_task.title = "Task 1"
        in_progress_task.status = "in_progress"
        in_progress_task.closed_at = None
        mock_task_manager.get_task.return_value = in_progress_task

        with patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="T1"):
            result = await wait_tool.func(
                task_id="T1",
                timeout=0.1,   # Very short timeout
                poll_interval=0.05,
            )

        assert result["success"] is True
        assert result["completed"] is False
        assert result["timed_out"] is True
        assert result["wait_time"] > 0

    @pytest.mark.asyncio
    async def test_wait_for_nonexistent_task(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
    ) -> None:
        """wait_for_task with a task that can't be resolved returns error."""
        wait_tool = registry._tools["wait_for_task"]

        from gobby.storage.tasks import TaskNotFoundError

        with patch(
            "gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp",
            side_effect=TaskNotFoundError("T999", "Not found"),
        ):
            result = await wait_tool.func(task_id="T999")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_wait_completes_on_second_poll(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
    ) -> None:
        """wait_for_task detects completion after one poll cycle."""
        wait_tool = registry._tools["wait_for_task"]

        poll_count = {"n": 0}

        def get_task(task_id: str) -> MagicMock:
            poll_count["n"] += 1
            t = MagicMock()
            t.id = "T1"
            t.seq_num = 1
            t.title = "Task 1"
            t.closed_at = None
            if poll_count["n"] >= 3:
                t.status = "closed"
                t.closed_at = "2024-01-01T01:00:00Z"
            else:
                t.status = "in_progress"
            return t

        mock_task_manager.get_task.side_effect = get_task

        with patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="T1"):
            result = await wait_tool.func(
                task_id="T1",
                timeout=5.0,
                poll_interval=0.05,
            )

        assert result["success"] is True
        assert result["completed"] is True
        assert result["timed_out"] is False
        assert result["wait_time"] > 0


# ── 5. Orchestrate edge cases ────────────────────────────────────────


class TestOrchestrateEdgeCases:
    """Test edge cases in orchestrate_ready_tasks."""

    @pytest.mark.asyncio
    async def test_no_agent_runner(
        self,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
    ) -> None:
        """orchestrate_ready_tasks fails gracefully without agent_runner."""
        registry = create_orchestration_registry(
            task_manager=mock_task_manager,
            worktree_storage=mock_worktree_storage,
            agent_runner=None,
            project_id=PROJECT_ID,
        )
        tool = registry._tools["orchestrate_ready_tasks"]

        with patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
            )

        assert result["success"] is False
        assert "not configured" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_parent_session_id(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
    ) -> None:
        """orchestrate_ready_tasks requires parent_session_id."""
        tool = registry._tools["orchestrate_ready_tasks"]

        with patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=None,
            )

        assert result["success"] is False
        assert "parent_session_id" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_parent_task_id(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
    ) -> None:
        """orchestrate_ready_tasks with invalid parent_task_id returns error."""
        tool = registry._tools["orchestrate_ready_tasks"]

        # resolve_task_id_for_mcp is captured in the closure, so we must make
        # the mock task_manager return None for get_task to trigger TaskNotFoundError
        mock_task_manager.get_task.return_value = None

        result = await tool.func(
            parent_task_id="INVALID",
            parent_session_id=PARENT_SESSION,
        )

        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_ready_tasks(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        workflow_state: None,
    ) -> None:
        """orchestrate_ready_tasks with no ready tasks returns empty success."""
        tool = registry._tools["orchestrate_ready_tasks"]

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
            )

        assert result["success"] is True
        assert result["spawned"] == []

    @pytest.mark.asyncio
    async def test_invalid_mode(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
    ) -> None:
        """orchestrate_ready_tasks rejects invalid mode parameter."""
        tool = registry._tools["orchestrate_ready_tasks"]

        with patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="PARENT"):
            result = await tool.func(
                parent_task_id="PARENT",
                parent_session_id=PARENT_SESSION,
                mode="invalid_mode",
            )

        assert result["success"] is False
        assert "invalid mode" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_task_already_has_active_worktree_skipped(
        self,
        registry: InternalToolRegistry,
        mock_task_manager: MagicMock,
        mock_worktree_storage: MagicMock,
        mock_git_manager: MagicMock,
        mock_agent_runner: MagicMock,
        workflow_state: None,
    ) -> None:
        """Task with existing active worktree is skipped."""
        tool = registry._tools["orchestrate_ready_tasks"]
        tasks = [_make_task("T1", "Task 1")]

        existing_wt = MagicMock()
        existing_wt.id = "existing-wt"
        existing_wt.agent_session_id = "some-active-session"
        mock_worktree_storage.get_by_task.return_value = existing_wt
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
            )

        assert result["success"] is True
        assert result["spawned_count"] == 0
        assert result["skipped_count"] == 1
        assert "active worktree" in result["skipped"][0]["reason"].lower()
