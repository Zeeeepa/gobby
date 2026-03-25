"""Tests for AgentRunner and AgentRunContext."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.agents.registry import RunningAgent
from gobby.agents.runner import AgentRunner
from gobby.agents.runner_models import AgentConfig, AgentRunContext
from gobby.hooks.events import HookResponse
from gobby.llm.executor import AgentResult, ToolResult

pytestmark = pytest.mark.unit


class TestAgentRunContext:
    """Tests for AgentRunContext dataclass."""

    def test_default_values(self) -> None:
        """All fields default to None."""
        ctx = AgentRunContext()

        assert ctx.session is None
        assert ctx.run is None
        assert ctx.session_id is None
        assert ctx.run_id is None

    def test_session_id_property(self) -> None:
        """session_id property returns session.id."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"

        ctx = AgentRunContext(session=mock_session)

        assert ctx.session_id == "sess-123"

    def test_session_id_none_when_no_session(self) -> None:
        """session_id returns None when session is None."""
        ctx = AgentRunContext()

        assert ctx.session_id is None

    def test_run_id_property(self) -> None:
        """run_id property returns run.id."""
        mock_run = MagicMock()
        mock_run.id = "run-456"

        ctx = AgentRunContext(run=mock_run)

        assert ctx.run_id == "run-456"

    def test_run_id_none_when_no_run(self) -> None:
        """run_id returns None when run is None."""
        ctx = AgentRunContext()

        assert ctx.run_id is None

    def test_all_fields_settable(self) -> None:
        """All fields can be set."""
        mock_session = MagicMock()
        mock_run = MagicMock()

        ctx = AgentRunContext(
            session=mock_session,
            run=mock_run,
        )

        assert ctx.session is mock_session
        assert ctx.run is mock_run


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_prompt_required(self) -> None:
        """prompt is the only required field."""
        config = AgentConfig(prompt="Do something")

        assert config.prompt == "Do something"

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        config = AgentConfig(prompt="test")

        assert config.parent_session_id is None
        assert config.project_id is None
        assert config.machine_id is None
        assert config.source == "claude"
        assert config.workflow is None
        assert config.task is None
        assert config.session_context == "summary_markdown"
        assert config.mode == "in_process"
        assert config.worktree_id is None
        assert config.provider == "claude"
        assert config.model is None
        assert config.max_turns == 10
        assert config.timeout == 120.0

    def test_get_effective_workflow_returns_workflow(self) -> None:
        """get_effective_workflow returns the workflow field."""
        config = AgentConfig(
            prompt="test",
            workflow="new-workflow",
        )

        assert config.get_effective_workflow() == "new-workflow"

    def test_get_effective_workflow_none(self) -> None:
        """get_effective_workflow returns None when neither set."""
        config = AgentConfig(prompt="test")

        assert config.get_effective_workflow() is None


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock()


@pytest.fixture
def mock_session_storage():
    """Create a mock session storage."""
    storage = MagicMock()
    # Mock get() for parent session lookup
    parent_session = MagicMock()
    parent_session.id = "sess-parent"
    parent_session.agent_depth = 0
    storage.get.return_value = parent_session
    return storage


@pytest.fixture
def mock_executor():
    """Create a mock agent executor."""
    executor = MagicMock()
    executor.run = AsyncMock(
        return_value=AgentResult(
            output="Task completed",
            status="success",
            turns_used=2,
            tool_calls=[],
        )
    )
    return executor


@pytest.fixture
def runner(mock_db, mock_session_storage, mock_executor):
    """Create an AgentRunner with mocked dependencies."""
    return AgentRunner(
        db=mock_db,
        session_storage=mock_session_storage,
        executors={"claude": mock_executor},
        max_agent_depth=2,
    )


class TestAgentRunnerPrepareRun:
    """Tests for AgentRunner.prepare_run()."""

    def test_prepare_run_validates_parent_session_id(self, runner) -> None:
        """prepare_run returns error when parent_session_id is missing."""
        config = AgentConfig(
            prompt="Test prompt",
            project_id="proj-123",
            machine_id="machine-1",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentResult)
        assert result.status == "error"
        assert "parent_session_id is required" in result.error

    def test_prepare_run_validates_project_id(self, runner) -> None:
        """prepare_run returns error when project_id is missing."""
        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            machine_id="machine-1",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentResult)
        assert result.status == "error"
        assert "project_id is required" in result.error

    def test_prepare_run_validates_machine_id(self, runner) -> None:
        """prepare_run returns error when machine_id is missing."""
        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentResult)
        assert result.status == "error"
        assert "machine_id is required" in result.error

    def test_prepare_run_creates_context(self, runner, mock_session_storage) -> None:
        """prepare_run creates AgentRunContext with session and run."""
        # Mock can_spawn to allow spawning
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        # Mock the child session manager to return a session
        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        # Mock the run storage
        agent_run = MagicMock()
        agent_run.id = "run-123"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentRunContext)
        assert result.session is child_session
        assert result.run is agent_run
        assert result.session_id == "sess-child"
        assert result.run_id == "run-123"

    def test_prepare_run_checks_spawn_depth(self, runner) -> None:
        """prepare_run checks agent depth limit."""
        # Make can_spawn return False
        runner._child_session_manager.can_spawn_child = MagicMock(
            return_value=(False, "Maximum agent depth exceeded", 2)
        )

        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentResult)
        assert result.status == "error"
        assert "depth exceeded" in result.error


class TestAgentRunnerExecuteRun:
    """Tests for AgentRunner.execute_run()."""

    async def test_execute_run_validates_context(self, runner):
        """execute_run returns error for invalid context."""
        config = AgentConfig(prompt="Test")
        context = AgentRunContext()  # Empty context

        result = await runner.execute_run(context, config)

        assert result.status == "error"
        assert "Invalid context" in result.error

    async def test_execute_run_checks_executor(self, runner):
        """execute_run returns error when executor not found."""
        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="unknown_provider")

        result = await runner.execute_run(context, config)

        assert result.status == "error"
        assert "No executor registered" in result.error

    async def test_execute_run_uses_prepared_context(self, runner, mock_executor):
        """execute_run uses the pre-prepared session and run."""
        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test task", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "success"
        assert result.output == "Task completed"
        mock_executor.run.assert_called_once()

    async def test_execute_run_updates_run_status(self, runner, mock_executor):
        """execute_run updates run record status on completion."""
        mock_session = MagicMock()
        mock_session.id = "sess-child"
        mock_run = MagicMock()
        mock_run.id = "run-123"

        runner._run_storage.start = MagicMock()
        runner._run_storage.complete = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        await runner.execute_run(context, config)

        runner._run_storage.start.assert_called_once_with("run-123")
        runner._run_storage.complete.assert_called_once()


class TestAgentRunnerRun:
    """Tests for AgentRunner.run() - backward compatibility."""

    async def test_run_combines_prepare_and_execute(self, runner, mock_executor):
        """run() calls prepare_run then execute_run."""
        # Mock can_spawn to allow spawning
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        # Setup child session manager
        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        # Setup run storage
        agent_run = MagicMock()
        agent_run.id = "run-123"
        runner._run_storage.create = MagicMock(return_value=agent_run)
        runner._run_storage.start = MagicMock()
        runner._run_storage.complete = MagicMock()

        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
        )

        result = await runner.run(config)

        assert result.status == "success"
        assert result.run_id == "run-123"

    async def test_run_returns_prepare_error(self, runner):
        """run() returns error if prepare_run fails."""
        config = AgentConfig(
            prompt="Test prompt",
            # Missing required fields
        )

        result = await runner.run(config)

        assert result.status == "error"
        assert "required" in result.error

    async def test_run_sets_run_id_on_result(self, runner, mock_executor):
        """run() sets run_id on the result."""
        # Mock can_spawn to allow spawning
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        agent_run = MagicMock()
        agent_run.id = "run-abc"
        runner._run_storage.create = MagicMock(return_value=agent_run)
        runner._run_storage.start = MagicMock()
        runner._run_storage.complete = MagicMock()

        config = AgentConfig(
            prompt="Test",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
        )

        result = await runner.run(config)

        assert result.run_id == "run-abc"


class TestAgentRunnerTerminalPickupMetadata:
    """Tests for terminal pickup metadata in prepare_run."""

    def test_prepare_run_sets_terminal_pickup_metadata(self, runner, mock_session_storage) -> None:
        """prepare_run calls update_terminal_pickup_metadata with correct values."""
        # Mock can_spawn to allow spawning
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        # Mock the child session manager to return a session
        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        # Mock the run storage
        agent_run = MagicMock()
        agent_run.id = "run-123"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        # Mock the session storage's update method
        mock_session_storage.update_terminal_pickup_metadata = MagicMock()

        from gobby.workflows.definitions import PipelineDefinition

        mock_pipeline = MagicMock(spec=PipelineDefinition)
        mock_pipeline.type = "pipeline"
        mock_pipeline.name = "legacy-workflow"
        runner._workflow_loader = MagicMock()
        runner._workflow_loader.load_workflow_sync = MagicMock(return_value=mock_pipeline)

        config = AgentConfig(
            prompt="Test prompt for agent",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            workflow="plan-execute",
        )

        result = runner.prepare_run(config)

        # Verify prepare_run succeeded
        assert isinstance(result, AgentRunContext)

        # Verify update_terminal_pickup_metadata was called with correct values
        mock_session_storage.update_terminal_pickup_metadata.assert_called_once_with(
            session_id="sess-child",
            workflow_name="plan-execute",
            agent_run_id="run-123",
            context_injected=False,
            original_prompt="Test prompt for agent",
        )

    def test_prepare_run_sets_metadata_without_workflow(self, runner, mock_session_storage) -> None:
        """prepare_run sets metadata even when no workflow specified."""
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        agent_run = MagicMock()
        agent_run.id = "run-456"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        mock_session_storage.update_terminal_pickup_metadata = MagicMock()

        config = AgentConfig(
            prompt="Simple task",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            # No workflow specified
        )

        runner.prepare_run(config)

        mock_session_storage.update_terminal_pickup_metadata.assert_called_once_with(
            session_id="sess-child",
            workflow_name=None,
            agent_run_id="run-456",
            context_injected=False,
            original_prompt="Simple task",
        )

    def test_prepare_run_uses_workflow_field(self, runner, mock_session_storage) -> None:
        """prepare_run passes workflow to session metadata."""
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        agent_run = MagicMock()
        agent_run.id = "run-789"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        mock_session_storage.update_terminal_pickup_metadata = MagicMock()

        from gobby.workflows.definitions import PipelineDefinition

        mock_pipeline = MagicMock(spec=PipelineDefinition)
        mock_pipeline.type = "pipeline"
        mock_pipeline.name = "legacy-workflow"
        runner._workflow_loader = MagicMock()
        runner._workflow_loader.load_workflow_sync = MagicMock(return_value=mock_pipeline)

        config = AgentConfig(
            prompt="Legacy workflow task",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            workflow="legacy-workflow",
        )

        runner.prepare_run(config)

        mock_session_storage.update_terminal_pickup_metadata.assert_called_once_with(
            session_id="sess-child",
            workflow_name="legacy-workflow",
            agent_run_id="run-789",
            context_injected=False,
            original_prompt="Legacy workflow task",
        )


class TestRunningAgent:
    """Tests for RunningAgent dataclass (from gobby.agents.registry)."""

    def test_create_running_agent(self) -> None:
        """RunningAgent stores all fields correctly."""
        agent = RunningAgent(
            run_id="run-123",
            session_id="sess-child",
            parent_session_id="sess-parent",
            mode="terminal",
            provider="claude",
            workflow_name="plan-execute",
            worktree_id="wt-abc",
            pid=12345,
            terminal_type="ghostty",
            master_fd=5,
        )

        assert agent.run_id == "run-123"
        assert agent.session_id == "sess-child"
        assert agent.parent_session_id == "sess-parent"
        assert agent.provider == "claude"
        assert agent.workflow_name == "plan-execute"
        assert agent.worktree_id == "wt-abc"
        assert agent.mode == "terminal"
        assert agent.pid == 12345
        assert agent.terminal_type == "ghostty"
        assert agent.master_fd == 5

    def test_running_agent_defaults(self) -> None:
        """RunningAgent has correct default values."""
        agent = RunningAgent(
            run_id="run-1",
            session_id="sess-c",
            parent_session_id="sess-p",
            mode="in_process",
        )

        assert agent.workflow_name is None
        assert agent.worktree_id is None
        assert agent.pid is None
        assert agent.terminal_type is None
        assert agent.master_fd is None
        assert agent.provider == "claude"
        assert agent.task is None

    def test_to_dict(self) -> None:
        """RunningAgent.to_dict() returns correct dict."""
        agent = RunningAgent(
            run_id="run-abc",
            session_id="sess-c",
            parent_session_id="sess-p",
            mode="autonomous",
            provider="claude",
        )

        result = agent.to_dict()

        assert result["run_id"] == "run-abc"
        assert result["parent_session_id"] == "sess-p"
        assert result["session_id"] == "sess-c"
        assert result["provider"] == "claude"
        assert result["mode"] == "autonomous"
        assert "started_at" in result


class TestAgentRunnerGetAndListRuns:
    """Tests for AgentRunner.get_run() and list_runs()."""

    def test_get_run_returns_run(self, runner) -> None:
        """get_run returns the run from storage."""
        mock_run = MagicMock()
        mock_run.id = "run-abc"
        runner._run_storage.get = MagicMock(return_value=mock_run)

        result = runner.get_run("run-abc")

        assert result is mock_run
        runner._run_storage.get.assert_called_once_with("run-abc")

    def test_get_run_returns_none_for_missing(self, runner) -> None:
        """get_run returns None when run not found."""
        runner._run_storage.get = MagicMock(return_value=None)

        result = runner.get_run("nonexistent")

        assert result is None

    def test_list_runs_returns_runs(self, runner) -> None:
        """list_runs returns runs from storage."""
        mock_runs = [MagicMock(), MagicMock()]
        runner._run_storage.list_by_session = MagicMock(return_value=mock_runs)

        result = runner.list_runs("sess-parent", status="running", limit=50)

        assert result == mock_runs
        runner._run_storage.list_by_session.assert_called_once_with(
            "sess-parent",
            status="running",
            limit=50,
        )

    def test_list_runs_uses_defaults(self, runner) -> None:
        """list_runs uses default values for status and limit."""
        runner._run_storage.list_by_session = MagicMock(return_value=[])

        runner.list_runs("sess-parent")

        runner._run_storage.list_by_session.assert_called_once_with(
            "sess-parent",
            status=None,
            limit=100,
        )


class TestAgentRunnerCancelRun:
    """Tests for AgentRunner.cancel_run()."""

    def test_cancel_run_success(self, runner, mock_session_storage) -> None:
        """cancel_run cancels a running agent."""
        mock_run = MagicMock()
        mock_run.id = "run-cancel"
        mock_run.status = "running"
        mock_run.child_session_id = "sess-child"
        runner._run_storage.get = MagicMock(return_value=mock_run)
        runner._run_storage.cancel = MagicMock()

        result = runner.cancel_run("run-cancel")

        assert result is True
        runner._run_storage.cancel.assert_called_once_with("run-cancel")
        mock_session_storage.update_status.assert_called_once_with("sess-child", "cancelled")

    def test_cancel_run_not_found(self, runner) -> None:
        """cancel_run returns False when run not found."""
        runner._run_storage.get = MagicMock(return_value=None)

        result = runner.cancel_run("nonexistent")

        assert result is False

    def test_cancel_run_not_running(self, runner) -> None:
        """cancel_run returns False when run is not in running status."""
        mock_run = MagicMock()
        mock_run.id = "run-done"
        mock_run.status = "success"  # Not running
        runner._run_storage.get = MagicMock(return_value=mock_run)

        result = runner.cancel_run("run-done")

        assert result is False

    def test_cancel_run_marks_db_cancelled(self, runner, mock_session_storage) -> None:
        """cancel_run marks the DB record as cancelled."""
        mock_run = MagicMock()
        mock_run.id = "run-tracked"
        mock_run.status = "running"
        mock_run.child_session_id = "sess-child"
        runner._run_storage.get = MagicMock(return_value=mock_run)
        runner._run_storage.cancel = MagicMock()

        result = runner.cancel_run("run-tracked")

        assert result is True
        runner._run_storage.cancel.assert_called_once_with("run-tracked")

    def test_cancel_run_no_child_session(self, runner) -> None:
        """cancel_run handles case where run has no child_session_id."""
        mock_run = MagicMock()
        mock_run.id = "run-no-child"
        mock_run.status = "running"
        mock_run.child_session_id = None
        runner._run_storage.get = MagicMock(return_value=mock_run)
        runner._run_storage.cancel = MagicMock()

        result = runner.cancel_run("run-no-child")

        assert result is True
        runner._run_storage.cancel.assert_called_once_with("run-no-child")

    def test_cancel_run_pending_agent(self, runner, mock_session_storage) -> None:
        """cancel_run cancels a pending agent (not yet running)."""
        mock_run = MagicMock()
        mock_run.id = "run-pending"
        mock_run.status = "pending"
        mock_run.child_session_id = "sess-child"
        runner._run_storage.get = MagicMock(return_value=mock_run)
        runner._run_storage.cancel = MagicMock()

        result = runner.cancel_run("run-pending")

        assert result is True
        runner._run_storage.cancel.assert_called_once_with("run-pending")
        mock_session_storage.update_status.assert_called_once_with("sess-child", "cancelled")


class TestAgentRunnerRegisterExecutor:
    """Tests for AgentRunner.register_executor()."""

    def test_register_executor(self, runner) -> None:
        """register_executor adds executor for provider."""
        mock_executor = MagicMock()

        runner.register_executor("gemini", mock_executor)

        assert runner._executors["gemini"] is mock_executor
        assert runner.get_executor("gemini") is mock_executor

    def test_register_executor_overwrites_existing(self, runner) -> None:
        """register_executor overwrites existing executor."""
        old_executor = MagicMock()
        new_executor = MagicMock()
        runner._executors["test"] = old_executor

        runner.register_executor("test", new_executor)

        assert runner.get_executor("test") is new_executor


class TestAgentRunnerDBTracking:
    """Tests for AgentRunner DB-driven running agents tracking."""

    def test_get_running_agent(self, runner) -> None:
        """get_running_agent returns running agent from DB."""
        mock_run = MagicMock()
        mock_run.id = "run-get"
        mock_run.status = "running"
        runner._run_storage.get = MagicMock(return_value=mock_run)

        agent = runner.get_running_agent("run-get")

        assert agent is not None
        assert agent.id == "run-get"

    def test_get_running_agent_not_found(self, runner) -> None:
        """get_running_agent returns None for missing agent."""
        runner._run_storage.get = MagicMock(return_value=None)

        agent = runner.get_running_agent("missing")

        assert agent is None

    def test_get_running_agent_completed_returns_none(self, runner) -> None:
        """get_running_agent returns None for non-running agent."""
        mock_run = MagicMock()
        mock_run.id = "run-done"
        mock_run.status = "success"
        runner._run_storage.get = MagicMock(return_value=mock_run)

        agent = runner.get_running_agent("run-done")

        assert agent is None

    def test_get_running_agents(self, runner) -> None:
        """get_running_agents returns all active agents from DB."""
        mock_runs = [MagicMock(id="run-1"), MagicMock(id="run-2")]
        runner._run_storage.list_active = MagicMock(return_value=mock_runs)

        agents = runner.get_running_agents()

        assert len(agents) == 2
        runner._run_storage.list_active.assert_called_once()

    def test_get_running_agents_filter_by_parent(self, runner) -> None:
        """get_running_agents filters by parent_session_id via DB."""
        mock_runs = [MagicMock(id="run-a")]
        runner._run_storage.list_by_parent = MagicMock(return_value=mock_runs)

        agents = runner.get_running_agents(parent_session_id="parent-1")

        assert len(agents) == 1
        runner._run_storage.list_by_parent.assert_called_once_with("parent-1")

    def test_get_running_agents_count(self, runner) -> None:
        """get_running_agents_count returns correct count from DB."""
        runner._run_storage.list_active = MagicMock(return_value=[])
        assert runner.get_running_agents_count() == 0

        runner._run_storage.list_active = MagicMock(return_value=[MagicMock()])
        assert runner.get_running_agents_count() == 1

    def test_is_agent_running(self, runner) -> None:
        """is_agent_running checks DB status."""
        runner._run_storage.get = MagicMock(return_value=None)
        assert runner.is_agent_running("run-check") is False

        mock_run = MagicMock()
        mock_run.status = "running"
        runner._run_storage.get = MagicMock(return_value=mock_run)
        assert runner.is_agent_running("run-check") is True


class TestAgentRunnerExecuteRunStatusHandling:
    """Tests for execute_run handling of different result statuses."""

    async def test_execute_run_handles_timeout_status(self, runner, mock_executor):
        """execute_run handles timeout status correctly."""
        mock_session = MagicMock()
        mock_session.id = "sess-timeout"
        mock_run = MagicMock()
        mock_run.id = "run-timeout"

        # Make executor return timeout status
        mock_executor.run = AsyncMock(
            return_value=AgentResult(
                output="Timed out",
                status="timeout",
                turns_used=5,
                tool_calls=[],
            )
        )

        runner._run_storage.start = MagicMock()
        runner._run_storage.timeout = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "timeout"
        runner._run_storage.timeout.assert_called_once_with("run-timeout", turns_used=5)

    async def test_execute_run_handles_error_status(
        self, runner, mock_executor, mock_session_storage
    ):
        """execute_run handles error status correctly."""
        mock_session = MagicMock()
        mock_session.id = "sess-error"
        mock_run = MagicMock()
        mock_run.id = "run-error"

        # Make executor return error status
        mock_executor.run = AsyncMock(
            return_value=AgentResult(
                output="",
                status="error",
                error="Something went wrong",
                turns_used=3,
                tool_calls=[],
            )
        )

        runner._run_storage.start = MagicMock()
        runner._run_storage.fail = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "error"
        assert result.error == "Something went wrong"
        runner._run_storage.fail.assert_called_once_with(
            "run-error",
            error="Something went wrong",
            tool_calls_count=0,
            turns_used=3,
        )
        mock_session_storage.update_status.assert_called_once_with("sess-error", "failed")

    async def test_execute_run_handles_partial_status(
        self, runner, mock_executor, mock_session_storage
    ):
        """execute_run handles partial status correctly."""
        mock_session = MagicMock()
        mock_session.id = "sess-partial"
        mock_run = MagicMock()
        mock_run.id = "run-partial"

        # Make executor return partial status
        mock_executor.run = AsyncMock(
            return_value=AgentResult(
                output="Partial result",
                status="partial",
                turns_used=2,
                tool_calls=[],
            )
        )

        runner._run_storage.start = MagicMock()
        runner._run_storage.complete = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "partial"
        runner._run_storage.complete.assert_called_once()
        mock_session_storage.update_status.assert_called_once_with("sess-partial", "completed")

    async def test_execute_run_handles_exception(self, runner, mock_executor, mock_session_storage):
        """execute_run handles executor exceptions correctly."""
        mock_session = MagicMock()
        mock_session.id = "sess-exc"
        mock_run = MagicMock()
        mock_run.id = "run-exc"

        # Make executor raise an exception
        mock_executor.run = AsyncMock(side_effect=RuntimeError("LLM API Error"))

        runner._run_storage.start = MagicMock()
        runner._run_storage.fail = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        result = await runner.execute_run(context, config)

        assert result.status == "error"
        assert "LLM API Error" in result.error
        runner._run_storage.fail.assert_called_once_with(
            "run-exc",
            error="LLM API Error",
            tool_calls_count=0,
            turns_used=0,
        )
        mock_session_storage.update_status.assert_called_once_with("sess-exc", "failed")

    async def test_execute_run_removes_from_tracking_on_exception(self, runner, mock_executor):
        """execute_run removes agent from tracking on exception."""
        mock_session = MagicMock()
        mock_session.id = "sess-exc-track"
        mock_run = MagicMock()
        mock_run.id = "run-exc-track"

        mock_executor.run = AsyncMock(side_effect=RuntimeError("Crash"))

        runner._run_storage.start = MagicMock()
        runner._run_storage.fail = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        # Run should add to tracking, then remove on exception
        await runner.execute_run(context, config)

        # Verify not in tracking after exception
        assert not runner.is_agent_running("run-exc-track")


class TestAgentRunnerHookIntegration:
    """Tests for workflow handler hook integration in execute_run."""

    @pytest.fixture
    def tool_results(self):
        """Track tool results captured by the executor."""
        return []

    @pytest.fixture
    def failing_tool_handler(self):
        """Tool handler that returns a failure."""

        async def handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error="column 'foo' does not exist",
            )

        return handler

    @pytest.fixture
    def succeeding_tool_handler(self):
        """Tool handler that returns success."""

        async def handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(
                tool_name=tool_name,
                success=True,
                result="query returned 3 rows",
            )

        return handler

    @pytest.fixture
    def capturing_executor(self, tool_results):
        """Executor that invokes the tool handler once and captures the result."""

        executor = MagicMock()

        async def run_impl(
            prompt,
            tools,
            tool_handler,
            system_prompt=None,
            model=None,
            max_turns=10,
            timeout=120.0,
        ):
            # Simulate a single tool call
            result = await tool_handler("Bash", {"command": "sqlite3 test.db"})
            tool_results.append(result)
            return AgentResult(
                output="done",
                status="success",
                turns_used=1,
                tool_calls=[],
            )

        executor.run = AsyncMock(side_effect=run_impl)
        return executor

    @pytest.fixture
    def mock_workflow_handler(self):
        """Mock workflow handler that returns recovery context."""
        handler = MagicMock()
        handler.evaluate = MagicMock(
            return_value=HookResponse(
                context="Recovery guidance: try a different approach",
            )
        )
        return handler

    @pytest.fixture
    def hook_runner(self, mock_db, mock_session_storage, capturing_executor):
        """AgentRunner with a capturing executor."""
        return AgentRunner(
            db=mock_db,
            session_storage=mock_session_storage,
            executors={"claude": capturing_executor},
            max_agent_depth=2,
        )

    def _make_context(self):
        """Create a valid AgentRunContext for tests."""
        mock_session = MagicMock()
        mock_session.id = "sess-hook-test"
        mock_run = MagicMock()
        mock_run.id = "run-hook-test"
        return AgentRunContext(session=mock_session, run=mock_run)

    async def test_hook_enriches_failed_tool_error(
        self,
        hook_runner,
        mock_workflow_handler,
        failing_tool_handler,
        capturing_executor,
        tool_results,
    ):
        """When workflow_handler is set and tool fails, error is enriched with context."""
        hook_runner.workflow_handler = mock_workflow_handler

        # Re-wire executor to use the failing handler
        async def run_impl(
            prompt,
            tools,
            tool_handler,
            system_prompt=None,
            model=None,
            max_turns=10,
            timeout=120.0,
        ):
            result = await tool_handler("Bash", {"command": "sqlite3 test.db"})
            tool_results.append(result)
            return AgentResult(output="done", status="success", turns_used=1, tool_calls=[])

        capturing_executor.run = AsyncMock(side_effect=run_impl)

        config = AgentConfig(prompt="Test", provider="claude")
        context = self._make_context()

        await hook_runner.execute_run(context, config, tool_handler=failing_tool_handler)

        # The tool result should have the original error + injected context
        assert len(tool_results) == 1
        assert "column 'foo' does not exist" in tool_results[0].error
        assert "Recovery guidance" in tool_results[0].error
        mock_workflow_handler.evaluate.assert_called_once()

    async def test_hook_enriches_success_result(
        self,
        hook_runner,
        mock_workflow_handler,
        succeeding_tool_handler,
        capturing_executor,
        tool_results,
    ):
        """When workflow_handler is set and tool succeeds, result gets context appended."""
        hook_runner.workflow_handler = mock_workflow_handler

        async def run_impl(
            prompt,
            tools,
            tool_handler,
            system_prompt=None,
            model=None,
            max_turns=10,
            timeout=120.0,
        ):
            result = await tool_handler("Bash", {"command": "echo hi"})
            tool_results.append(result)
            return AgentResult(output="done", status="success", turns_used=1, tool_calls=[])

        capturing_executor.run = AsyncMock(side_effect=run_impl)

        config = AgentConfig(prompt="Test", provider="claude")
        context = self._make_context()

        await hook_runner.execute_run(context, config, tool_handler=succeeding_tool_handler)

        assert len(tool_results) == 1
        assert "query returned 3 rows" in str(tool_results[0].result)
        assert "Recovery guidance" in str(tool_results[0].result)

    async def test_no_handler_works_without_enrichment(
        self,
        hook_runner,
        failing_tool_handler,
        capturing_executor,
        tool_results,
    ):
        """When workflow_handler is None, tool results pass through unmodified."""
        assert hook_runner.workflow_handler is None

        async def run_impl(
            prompt,
            tools,
            tool_handler,
            system_prompt=None,
            model=None,
            max_turns=10,
            timeout=120.0,
        ):
            result = await tool_handler("Bash", {"command": "bad cmd"})
            tool_results.append(result)
            return AgentResult(output="done", status="success", turns_used=1, tool_calls=[])

        capturing_executor.run = AsyncMock(side_effect=run_impl)

        config = AgentConfig(prompt="Test", provider="claude")
        context = self._make_context()

        await hook_runner.execute_run(context, config, tool_handler=failing_tool_handler)

        assert len(tool_results) == 1
        assert tool_results[0].error == "column 'foo' does not exist"
        assert "Recovery guidance" not in tool_results[0].error

    async def test_hook_eval_exception_is_fail_open(
        self,
        hook_runner,
        failing_tool_handler,
        capturing_executor,
        tool_results,
    ):
        """If workflow_handler.evaluate raises, the tool result passes through unmodified."""
        bad_handler = MagicMock()
        bad_handler.evaluate = MagicMock(side_effect=RuntimeError("handler crashed"))
        hook_runner.workflow_handler = bad_handler

        async def run_impl(
            prompt,
            tools,
            tool_handler,
            system_prompt=None,
            model=None,
            max_turns=10,
            timeout=120.0,
        ):
            result = await tool_handler("Bash", {"command": "bad cmd"})
            tool_results.append(result)
            return AgentResult(output="done", status="success", turns_used=1, tool_calls=[])

        capturing_executor.run = AsyncMock(side_effect=run_impl)

        config = AgentConfig(prompt="Test", provider="claude")
        context = self._make_context()

        await hook_runner.execute_run(context, config, tool_handler=failing_tool_handler)

        # Should still work, just without enrichment
        assert len(tool_results) == 1
        assert tool_results[0].error == "column 'foo' does not exist"
        assert "Recovery guidance" not in tool_results[0].error

    async def test_hook_no_context_leaves_result_unchanged(
        self,
        hook_runner,
        failing_tool_handler,
        capturing_executor,
        tool_results,
    ):
        """When workflow_handler returns no context, result is unchanged."""
        empty_handler = MagicMock()
        empty_handler.evaluate = MagicMock(return_value=HookResponse(context=None))
        hook_runner.workflow_handler = empty_handler

        async def run_impl(
            prompt,
            tools,
            tool_handler,
            system_prompt=None,
            model=None,
            max_turns=10,
            timeout=120.0,
        ):
            result = await tool_handler("Bash", {"command": "bad cmd"})
            tool_results.append(result)
            return AgentResult(output="done", status="success", turns_used=1, tool_calls=[])

        capturing_executor.run = AsyncMock(side_effect=run_impl)

        config = AgentConfig(prompt="Test", provider="claude")
        context = self._make_context()

        await hook_runner.execute_run(context, config, tool_handler=failing_tool_handler)

        assert len(tool_results) == 1
        assert tool_results[0].error == "column 'foo' does not exist"

    async def test_hook_event_has_correct_fields(
        self,
        hook_runner,
        failing_tool_handler,
        capturing_executor,
        tool_results,
    ):
        """Verify the HookEvent passed to evaluate has correct structure."""
        from gobby.hooks.events import HookEventType, SessionSource

        captured_events = []

        def capture_evaluate(event):
            captured_events.append(event)
            return HookResponse()

        handler = MagicMock()
        handler.evaluate = MagicMock(side_effect=capture_evaluate)
        hook_runner.workflow_handler = handler

        async def run_impl(
            prompt,
            tools,
            tool_handler,
            system_prompt=None,
            model=None,
            max_turns=10,
            timeout=120.0,
        ):
            result = await tool_handler("Bash", {"command": "sqlite3 test.db"})
            tool_results.append(result)
            return AgentResult(output="done", status="success", turns_used=1, tool_calls=[])

        capturing_executor.run = AsyncMock(side_effect=run_impl)

        config = AgentConfig(prompt="Test", provider="claude")
        context = self._make_context()

        await hook_runner.execute_run(context, config, tool_handler=failing_tool_handler)

        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.event_type == HookEventType.AFTER_TOOL
        assert event.source == SessionSource.AUTONOMOUS_SDK
        assert event.session_id == "sess-hook-test"
        assert event.data["tool_name"] == "Bash"
        assert event.data["is_error"] is True
        assert event.metadata["is_failure"] is True
