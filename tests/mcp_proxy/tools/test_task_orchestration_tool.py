from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.runner import AgentRunner
from gobby.mcp_proxy.tools.task_orchestration import (
    create_orchestration_registry,
)
from gobby.storage.sessions import Session
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.storage.worktrees import LocalWorktreeManager, Worktree
from gobby.worktrees.git import GitOperationResult, WorktreeGitManager

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_task_manager():
    m = MagicMock(spec=LocalTaskManager)
    m.db = MagicMock()
    return m


@pytest.fixture
def mock_worktree_storage():
    return MagicMock(spec=LocalWorktreeManager)


@pytest.fixture
def mock_git_manager():
    return MagicMock(spec=WorktreeGitManager)


@pytest.fixture
def mock_agent_runner():
    runner = MagicMock(spec=AgentRunner)
    # can_spawn returns (allowed, reason, depth)
    runner.can_spawn.return_value = (True, None, 1)
    # Explicitly mock internal manager since spec might not cover it
    runner._child_session_manager = MagicMock()
    runner._child_session_manager.max_agent_depth = 3
    return runner


@pytest.fixture
def orchestration_tools(
    mock_task_manager, mock_worktree_storage, mock_git_manager, mock_agent_runner
):
    return create_orchestration_registry(
        task_manager=mock_task_manager,
        worktree_storage=mock_worktree_storage,
        git_manager=mock_git_manager,
        agent_runner=mock_agent_runner,
        project_id="test-project",
    )


class TestOrchestrateReadyTasks:
    @pytest.mark.asyncio
    async def test_orchestrate_basic(
        self,
        orchestration_tools,
        mock_task_manager,
        mock_worktree_storage,
        mock_git_manager,
        mock_agent_runner,
    ):
        tool = orchestration_tools._tools["orchestrate_ready_tasks"]

        # Setup mocks
        subtask1 = Task(
            id="T2",
            title="Subtask 1",
            project_id="test-project",
            status="open",
            parent_task_id="T1",
            priority=2,
            task_type="task",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        # _get_ready_descendants mock
        with patch(
            "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
            return_value=[subtask1],
        ):
            with patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="T1"):
                # Mock worktrees list (none running)
                mock_worktree_storage.list_worktrees.return_value = []

                # Mock git worktree creation
                mock_git_manager.create_worktree.return_value = GitOperationResult(
                    success=True, message="Created"
                )
                mock_git_manager.repo_path = "/repo"

                # Mock worktree storage creation
                mock_wt = Worktree(
                    id="wt-1",
                    project_id="test-project",
                    branch_name="task/T2",
                    worktree_path="/tmp/wt-1",
                    base_branch="main",
                    task_id="T2",
                    agent_session_id="session-1",
                    status="active",
                    created_at="2024-01-01T00:00:00Z",
                    updated_at="2024-01-01T00:00:00Z",
                    merged_at=None,
                )
                mock_worktree_storage.create.return_value = mock_wt
                mock_worktree_storage.get_by_task.return_value = None
                mock_worktree_storage.get_by_branch.return_value = None

                # Mock agent preparation
                mock_session = MagicMock(spec=Session)
                mock_session.id = "session-1"
                mock_session.agent_depth = 1
                mock_run = MagicMock()
                mock_run.id = "run-1"

                prepare_result = MagicMock()
                prepare_result.session = mock_session
                prepare_result.run = mock_run
                mock_agent_runner.prepare_run.return_value = prepare_result

                # Mock spawner
                with patch("gobby.agents.spawn.TerminalSpawner") as MockSpawner:
                    spawner_instance = MockSpawner.return_value
                    spawner_instance.spawn_agent.return_value = MagicMock(
                        success=True, pid=123, terminal_type="mock"
                    )

                    # Mock helpers
                    with (
                        patch("gobby.mcp_proxy.tools.worktrees._copy_project_json_to_worktree"),
                        patch("gobby.mcp_proxy.tools.worktrees._install_provider_hooks"),
                        patch(
                            "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                            return_value="test-project",
                        ),
                    ):
                        result = await tool.func(
                            parent_task_id="T1", parent_session_id="parent-session"
                        )

                        assert "error" not in result
                        assert len(result["spawned"]) == 1
                        assert result["spawned"][0]["task_id"] == "T2"
                        assert result["spawned"][0]["pid"] == 123

                        # Verify claims
                        mock_worktree_storage.claim.assert_called_with("wt-1", "session-1")
                        mock_task_manager.update_task.assert_called_with("T2", status="in_progress")

    @pytest.mark.asyncio
    async def test_max_concurrent_limit(
        self, orchestration_tools, mock_task_manager, mock_worktree_storage
    ):
        tool = orchestration_tools._tools["orchestrate_ready_tasks"]

        # 3 tasks ready
        tasks = [
            Task(
                id=f"T{i}",
                title=f"Task {i}",
                project_id="test-project",
                priority=2,
                task_type="task",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
                status="open",
            )
            for i in range(3)
        ]

        with patch(
            "gobby.mcp_proxy.tools.orchestration.orchestrate._get_ready_descendants",
            return_value=tasks,
        ):
            with patch(
                "gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="T-Parent"
            ):
                with patch(
                    "gobby.mcp_proxy.tools.orchestration.orchestrate.get_current_project_id",
                    return_value="test-project",
                ):
                    # Mock 2 already running
                    running_wt1 = MagicMock(agent_session_id="sess-1")
                    running_wt2 = MagicMock(agent_session_id="sess-2")
                    mock_worktree_storage.list_worktrees.return_value = [running_wt1, running_wt2]

                    # Max concurrent = 3, so only 1 slot left
                    result = await tool.func(
                        parent_task_id="T-Parent",
                        parent_session_id="parent-session",
                        max_concurrent=3,
                    )

                    assert "error" not in result
                    # The logic: running=2, max=3, available=1.
                    # tasks_to_spawn = tasks[:1] (T0)
                    # tasks_skipped = tasks[1:] (T1, T2) -> added to skipped list with "max_concurrent limit reached"

                    # We expect T1 and T2 to be skipped due to limit.
                    skipped_reasons = {s["task_id"]: s["reason"] for s in result["skipped"]}
                    assert "T1" in skipped_reasons
                    assert skipped_reasons["T1"] == "max_concurrent limit reached"
                    assert "T2" in skipped_reasons
                    assert skipped_reasons["T2"] == "max_concurrent limit reached"


class TestGetOrchestrationStatus:
    @pytest.mark.asyncio
    async def test_get_status(self, orchestration_tools, mock_task_manager, mock_worktree_storage):
        tool = orchestration_tools._tools["get_orchestration_status"]

        parent = Task(
            id="P1",
            title="Parent",
            project_id="test-project",
            status="in_progress",
            priority=2,
            task_type="task",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        sub1 = Task(
            id="S1",
            title="Sub 1",
            project_id="test-project",
            status="open",
            priority=2,
            task_type="task",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            parent_task_id="P1",
        )
        sub2 = Task(
            id="S2",
            title="Sub 2",
            project_id="test-project",
            status="in_progress",
            priority=2,
            task_type="task",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            parent_task_id="P1",
        )
        sub3 = Task(
            id="S3",
            title="Sub 3",
            project_id="test-project",
            status="closed",
            priority=2,
            task_type="task",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            parent_task_id="P1",
        )

        mock_task_manager.get_task.return_value = parent
        mock_task_manager.list_tasks.return_value = [sub1, sub2, sub3]

        with patch("gobby.mcp_proxy.tools.tasks.resolve_task_id_for_mcp", return_value="P1"):
            with patch(
                "gobby.mcp_proxy.tools.orchestration.monitor.get_current_project_id",
                return_value="test-project",
            ):
                # Mock worktree for S2
                mock_wt = MagicMock(id="wt-s2", status="active", agent_session_id="sess-1")
                mock_worktree_storage.get_by_task.side_effect = (
                    lambda tid: mock_wt if tid == "S2" else None
                )

                result = await tool.func(parent_task_id="P1")

                assert "error" not in result
                assert result["summary"]["open"] == 1
                assert result["summary"]["in_progress"] == 1
                assert result["summary"]["closed"] == 1

                in_progress = result["in_progress_tasks"][0]
                assert in_progress["id"] == "S2"
                assert in_progress["worktree_id"] == "wt-s2"
                assert in_progress["has_active_agent"] is True
