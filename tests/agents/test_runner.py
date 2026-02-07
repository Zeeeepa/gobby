"""Tests for AgentRunner and AgentRunContext."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.agents.runner import AgentConfig, AgentRunContext, AgentRunner, RunningAgent
from gobby.llm.executor import AgentResult

pytestmark = pytest.mark.unit


class TestAgentRunContext:
    """Tests for AgentRunContext dataclass."""

    def test_default_values(self) -> None:
        """All fields default to None."""
        ctx = AgentRunContext()

        assert ctx.session is None
        assert ctx.run is None
        assert ctx.workflow_state is None
        assert ctx.workflow_config is None

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
        mock_state = MagicMock()
        mock_workflow = MagicMock()

        ctx = AgentRunContext(
            session=mock_session,
            run=mock_run,
            workflow_state=mock_state,
            workflow_config=mock_workflow,
        )

        assert ctx.session is mock_session
        assert ctx.run is mock_run
        assert ctx.workflow_state is mock_state
        assert ctx.workflow_config is mock_workflow


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
        assert config.terminal == "auto"
        assert config.worktree_id is None
        assert config.provider == "claude"
        assert config.model is None
        assert config.max_turns == 10
        assert config.timeout == 120.0

    def test_get_effective_workflow_prefers_workflow(self) -> None:
        """get_effective_workflow prefers 'workflow' over 'workflow_name'."""
        config = AgentConfig(
            prompt="test",
            workflow="new-workflow",
            workflow_name="old-workflow",
        )

        assert config.get_effective_workflow() == "new-workflow"

    def test_get_effective_workflow_fallback(self) -> None:
        """get_effective_workflow falls back to workflow_name."""
        config = AgentConfig(
            prompt="test",
            workflow_name="legacy-workflow",
        )

        assert config.get_effective_workflow() == "legacy-workflow"

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

    def test_prepare_run_uses_legacy_workflow_name(self, runner, mock_session_storage) -> None:
        """prepare_run uses legacy workflow_name if workflow not specified."""
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        agent_run = MagicMock()
        agent_run.id = "run-789"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        mock_session_storage.update_terminal_pickup_metadata = MagicMock()

        config = AgentConfig(
            prompt="Legacy workflow task",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            workflow_name="legacy-workflow",  # Using legacy field
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
            mode="headless",
            provider="claude",
        )

        result = agent.to_dict()

        assert result["run_id"] == "run-abc"
        assert result["parent_session_id"] == "sess-p"
        assert result["session_id"] == "sess-c"
        assert result["provider"] == "claude"
        assert result["mode"] == "headless"
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

    def test_cancel_run_removes_from_tracking(self, runner, mock_session_storage) -> None:
        """cancel_run removes agent from in-memory tracking."""
        mock_run = MagicMock()
        mock_run.id = "run-tracked"
        mock_run.status = "running"
        mock_run.child_session_id = "sess-child"
        runner._run_storage.get = MagicMock(return_value=mock_run)
        runner._run_storage.cancel = MagicMock()

        # Add to tracking first
        runner._running_agents["run-tracked"] = MagicMock()
        assert "run-tracked" in runner._running_agents

        result = runner.cancel_run("run-tracked")

        assert result is True
        assert "run-tracked" not in runner._running_agents

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


class TestAgentRunnerInMemoryTracking:
    """Tests for AgentRunner in-memory running agents tracking."""

    def test_track_running_agent(self, runner) -> None:
        """_track_running_agent adds agent to dict."""
        agent = runner._track_running_agent(
            run_id="run-123",
            parent_session_id="sess-parent",
            child_session_id="sess-child",
            provider="claude",
            prompt="Test task",
        )

        assert agent.run_id == "run-123"
        assert "run-123" in runner._running_agents
        assert runner._running_agents["run-123"] is agent

    def test_untrack_running_agent(self, runner) -> None:
        """_untrack_running_agent removes agent from dict."""
        runner._track_running_agent(
            run_id="run-456",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="claude",
            prompt="Task",
        )

        removed = runner._untrack_running_agent("run-456")

        assert removed is not None
        assert removed.run_id == "run-456"
        assert "run-456" not in runner._running_agents

    def test_untrack_nonexistent_returns_none(self, runner) -> None:
        """_untrack_running_agent returns None for missing agent."""
        result = runner._untrack_running_agent("nonexistent-run")

        assert result is None

    def test_update_running_agent(self, runner) -> None:
        """_update_running_agent returns agent if found.

        Note: The registry's RunningAgent is lightweight and doesn't track
        turns_used/tool_calls_count - those are tracked in the database.
        This method just verifies the agent exists.
        """
        runner._track_running_agent(
            run_id="run-789",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="claude",
            prompt="Task",
        )

        updated = runner._update_running_agent(
            "run-789",
            turns_used=5,
            tool_calls_count=10,
        )

        # Should return the agent (verifying it exists)
        assert updated is not None
        assert updated.run_id == "run-789"

    def test_get_running_agent(self, runner) -> None:
        """get_running_agent returns agent by ID."""
        runner._track_running_agent(
            run_id="run-get",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="claude",
            prompt="Task",
        )

        agent = runner.get_running_agent("run-get")

        assert agent is not None
        assert agent.run_id == "run-get"

    def test_get_running_agent_not_found(self, runner) -> None:
        """get_running_agent returns None for missing agent."""
        agent = runner.get_running_agent("missing")

        assert agent is None

    def test_get_running_agents(self, runner) -> None:
        """get_running_agents returns all agents."""
        runner._track_running_agent(
            run_id="run-1",
            parent_session_id="sess-p1",
            child_session_id="sess-c1",
            provider="claude",
            prompt="Task 1",
        )
        runner._track_running_agent(
            run_id="run-2",
            parent_session_id="sess-p2",
            child_session_id="sess-c2",
            provider="gemini",
            prompt="Task 2",
        )

        agents = runner.get_running_agents()

        assert len(agents) == 2
        run_ids = {a.run_id for a in agents}
        assert run_ids == {"run-1", "run-2"}

    def test_get_running_agents_filter_by_parent(self, runner) -> None:
        """get_running_agents filters by parent_session_id."""
        runner._track_running_agent(
            run_id="run-a",
            parent_session_id="parent-1",
            child_session_id="child-a",
            provider="claude",
            prompt="Task A",
        )
        runner._track_running_agent(
            run_id="run-b",
            parent_session_id="parent-2",
            child_session_id="child-b",
            provider="claude",
            prompt="Task B",
        )

        agents = runner.get_running_agents(parent_session_id="parent-1")

        assert len(agents) == 1
        assert agents[0].run_id == "run-a"

    def test_get_running_agents_count(self, runner) -> None:
        """get_running_agents_count returns correct count."""
        assert runner.get_running_agents_count() == 0

        runner._track_running_agent(
            run_id="run-1",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="claude",
            prompt="Task",
        )

        assert runner.get_running_agents_count() == 1

    def test_is_agent_running(self, runner) -> None:
        """is_agent_running returns correct boolean."""
        assert runner.is_agent_running("run-check") is False

        runner._track_running_agent(
            run_id="run-check",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="claude",
            prompt="Task",
        )

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
        assert "run-exc-track" not in runner._running_agents


class TestAgentRunnerPrepareRunWorkflows:
    """Tests for AgentRunner.prepare_run() workflow handling."""

    def test_prepare_run_rejects_lifecycle_workflow(self, runner, mock_session_storage) -> None:
        """prepare_run returns error for lifecycle workflows."""
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        # Mock the workflow loader to return a lifecycle workflow
        mock_workflow = MagicMock()
        mock_workflow.type = "lifecycle"
        runner._workflow_loader.load_workflow_sync = MagicMock(return_value=mock_workflow)

        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            workflow="lifecycle-workflow",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentResult)
        assert result.status == "error"
        assert "lifecycle workflow" in result.error.lower()
        assert "cannot use" in result.error.lower()

    def test_prepare_run_handles_child_session_creation_failure(
        self, runner, mock_session_storage
    ) -> None:
        """prepare_run handles ValueError from create_child_session."""
        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))
        runner._child_session_manager.create_child_session = MagicMock(
            side_effect=ValueError("Session creation failed")
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
        assert "Session creation failed" in result.error

    def test_prepare_run_warns_on_workflow_not_found(
        self, runner, mock_session_storage, caplog
    ) -> None:
        """prepare_run logs warning when workflow not found."""
        import logging

        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        agent_run = MagicMock()
        agent_run.id = "run-123"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        # Mock workflow loader to return None (not found)
        runner._workflow_loader.load_workflow_sync = MagicMock(return_value=None)

        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            workflow="nonexistent-workflow",
        )

        with caplog.at_level(logging.WARNING):
            result = runner.prepare_run(config)

        assert isinstance(result, AgentRunContext)
        assert "not found" in caplog.text or result.workflow_config is None

    def test_prepare_run_initializes_workflow_state(self, runner, mock_session_storage) -> None:
        """prepare_run initializes workflow state for step workflows."""
        from gobby.workflows.definitions import WorkflowDefinition

        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        agent_run = MagicMock()
        agent_run.id = "run-123"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        # Mock workflow loader to return a step workflow (must pass isinstance check)
        mock_step = MagicMock()
        mock_step.name = "plan"
        mock_workflow = MagicMock(spec=WorkflowDefinition)
        mock_workflow.type = "step"
        mock_workflow.steps = [mock_step]
        mock_workflow.variables = {"initial_var": "value"}
        runner._workflow_loader.load_workflow_sync = MagicMock(return_value=mock_workflow)

        # Mock the workflow state manager
        runner._workflow_state_manager.save_state = MagicMock()

        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            workflow="plan-execute",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentRunContext)
        assert result.workflow_config is mock_workflow
        runner._workflow_state_manager.save_state.assert_called_once()

    def test_prepare_run_handles_workflow_with_no_steps(self, runner, mock_session_storage) -> None:
        """prepare_run handles workflow with empty steps list."""
        from gobby.workflows.definitions import WorkflowDefinition

        runner._child_session_manager.can_spawn_child = MagicMock(return_value=(True, "OK", 0))

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(return_value=child_session)

        agent_run = MagicMock()
        agent_run.id = "run-123"
        runner._run_storage.create = MagicMock(return_value=agent_run)

        # Mock workflow loader to return a workflow with NO steps (must pass isinstance check)
        mock_workflow = MagicMock(spec=WorkflowDefinition)
        mock_workflow.type = "step"
        mock_workflow.steps = []  # Empty steps list
        mock_workflow.variables = {}
        runner._workflow_loader.load_workflow_sync = MagicMock(return_value=mock_workflow)

        runner._workflow_state_manager.save_state = MagicMock()

        config = AgentConfig(
            prompt="Test prompt",
            parent_session_id="sess-parent",
            project_id="proj-123",
            machine_id="machine-1",
            workflow="stepless-workflow",
        )

        result = runner.prepare_run(config)

        assert isinstance(result, AgentRunContext)
        # Verify workflow state was saved with empty step
        runner._workflow_state_manager.save_state.assert_called_once()
        saved_state = runner._workflow_state_manager.save_state.call_args[0][0]
        assert saved_state.step == ""


class TestAgentRunnerWorkflowFiltering:
    """Tests for workflow-based tool filtering in execute_run."""

    async def test_execute_run_with_workflow_filters_tools(
        self, runner, mock_executor, mock_session_storage
    ):
        """execute_run creates workflow-filtered handler when workflow is active."""
        mock_session = MagicMock()
        mock_session.id = "sess-workflow"
        mock_run = MagicMock()
        mock_run.id = "run-workflow"

        # Create a mock workflow definition
        mock_step = MagicMock()
        mock_step.name = "plan"
        mock_step.allowed_tools = ["create_task", "list_tasks"]
        mock_step.blocked_tools = []
        mock_workflow = MagicMock()
        mock_workflow.get_step = MagicMock(return_value=mock_step)

        runner._run_storage.start = MagicMock()
        runner._run_storage.complete = MagicMock()

        context = AgentRunContext(
            session=mock_session,
            run=mock_run,
            workflow_config=mock_workflow,
        )
        config = AgentConfig(prompt="Test", provider="claude")

        await runner.execute_run(context, config)

        # Verify executor was called
        mock_executor.run.assert_called_once()

    async def test_execute_run_default_tool_handler(self, runner, mock_executor):
        """execute_run uses default handler that returns not implemented."""
        mock_session = MagicMock()
        mock_session.id = "sess-default"
        mock_run = MagicMock()
        mock_run.id = "run-default"

        runner._run_storage.start = MagicMock()
        runner._run_storage.complete = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        # Capture the tool handler passed to executor
        captured_handler = None

        async def capture_handler(**kwargs):
            nonlocal captured_handler
            captured_handler = kwargs.get("tool_handler")
            return AgentResult(output="Done", status="success", turns_used=1, tool_calls=[])

        mock_executor.run = capture_handler

        await runner.execute_run(context, config)

        # Now test the default handler behavior
        assert captured_handler is not None

        result = await captured_handler("unknown_tool", {"arg": "value"})
        assert result.success is False
        assert "not implemented" in result.error.lower()

    async def test_execute_run_tracking_handler_counts_tools(self, runner, mock_executor):
        """execute_run tracking handler counts tool calls."""
        mock_session = MagicMock()
        mock_session.id = "sess-track"
        mock_run = MagicMock()
        mock_run.id = "run-track"

        runner._run_storage.start = MagicMock()
        runner._run_storage.complete = MagicMock()

        context = AgentRunContext(session=mock_session, run=mock_run)
        config = AgentConfig(prompt="Test", provider="claude")

        # Create a custom tool handler
        from gobby.llm.executor import ToolCallRecord, ToolResult

        async def custom_handler(tool_name: str, arguments: dict):
            return ToolResult(tool_name=tool_name, success=True, result="OK")

        # Make executor call the tool handler
        async def executor_that_calls_tools(**kwargs):
            handler = kwargs.get("tool_handler")
            await handler("tool1", {})
            await handler("tool2", {})
            return AgentResult(
                output="Done",
                status="success",
                turns_used=1,
                tool_calls=[
                    ToolCallRecord(tool_name="tool1", arguments={}),
                    ToolCallRecord(tool_name="tool2", arguments={}),
                ],
            )

        mock_executor.run = executor_that_calls_tools

        await runner.execute_run(context, config, tool_handler=custom_handler)

        # Tool calls should have been counted (via _update_running_agent)
        runner._run_storage.complete.assert_called_once()


class TestWorkflowFilteredHandler:
    """Tests for _create_workflow_filtered_handler."""

    async def test_filtered_handler_blocks_blocked_tools(self, runner):
        """Workflow filtered handler blocks tools in blocked_tools list."""
        from gobby.llm.executor import ToolResult
        from gobby.workflows.definitions import WorkflowState

        # Create mocks
        mock_step = MagicMock()
        mock_step.name = "execute"
        mock_step.allowed_tools = "all"
        mock_step.blocked_tools = ["dangerous_tool"]

        mock_workflow = MagicMock()
        mock_workflow.get_step = MagicMock(return_value=mock_step)

        mock_state = WorkflowState(
            session_id="sess-test",
            workflow_name="test-workflow",
            step="execute",
        )
        runner._workflow_state_manager.get_state = MagicMock(return_value=mock_state)

        async def base_handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(tool_name=tool_name, success=True, result="OK")

        handler = runner._create_workflow_filtered_handler(
            base_handler=base_handler,
            session_id="sess-test",
            workflow_definition=mock_workflow,
        )

        # Blocked tool should fail
        result = await handler("dangerous_tool", {})
        assert result.success is False
        assert "blocked" in result.error.lower()

    async def test_filtered_handler_allows_only_allowed_tools(self, runner):
        """Workflow filtered handler only allows tools in allowed_tools list."""
        from gobby.llm.executor import ToolResult
        from gobby.workflows.definitions import WorkflowState

        mock_step = MagicMock()
        mock_step.name = "plan"
        mock_step.allowed_tools = ["create_task", "list_tasks"]
        mock_step.blocked_tools = []

        mock_workflow = MagicMock()
        mock_workflow.get_step = MagicMock(return_value=mock_step)

        mock_state = WorkflowState(
            session_id="sess-test",
            workflow_name="test-workflow",
            step="plan",
        )
        runner._workflow_state_manager.get_state = MagicMock(return_value=mock_state)

        async def base_handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(tool_name=tool_name, success=True, result="OK")

        handler = runner._create_workflow_filtered_handler(
            base_handler=base_handler,
            session_id="sess-test",
            workflow_definition=mock_workflow,
        )

        # Allowed tool should succeed
        result = await handler("create_task", {"title": "Test", "session_id": "sess-test"})
        assert result.success is True

        # Not allowed tool should fail
        result = await handler("delete_file", {})
        assert result.success is False
        assert "not allowed" in result.error.lower()

    async def test_filtered_handler_passes_through_when_no_state(self, runner):
        """Workflow filtered handler passes through when no workflow state."""
        from gobby.llm.executor import ToolResult

        mock_workflow = MagicMock()
        runner._workflow_state_manager.get_state = MagicMock(return_value=None)

        async def base_handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(tool_name=tool_name, success=True, result="passed through")

        handler = runner._create_workflow_filtered_handler(
            base_handler=base_handler,
            session_id="sess-test",
            workflow_definition=mock_workflow,
        )

        result = await handler("any_tool", {})
        assert result.success is True
        assert result.result == "passed through"

    async def test_filtered_handler_passes_through_when_no_step(self, runner):
        """Workflow filtered handler passes through when step not found."""
        from gobby.llm.executor import ToolResult
        from gobby.workflows.definitions import WorkflowState

        mock_workflow = MagicMock()
        mock_workflow.get_step = MagicMock(return_value=None)

        mock_state = WorkflowState(
            session_id="sess-test",
            workflow_name="test-workflow",
            step="nonexistent",
        )
        runner._workflow_state_manager.get_state = MagicMock(return_value=mock_state)

        async def base_handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(tool_name=tool_name, success=True, result="passed through")

        handler = runner._create_workflow_filtered_handler(
            base_handler=base_handler,
            session_id="sess-test",
            workflow_definition=mock_workflow,
        )

        result = await handler("any_tool", {})
        assert result.success is True

    async def test_filtered_handler_handles_complete_tool(self, runner):
        """Workflow filtered handler handles 'complete' tool as exit condition."""
        from gobby.llm.executor import ToolResult
        from gobby.workflows.definitions import WorkflowState

        mock_step = MagicMock()
        mock_step.name = "execute"
        mock_step.allowed_tools = "all"
        mock_step.blocked_tools = []

        mock_workflow = MagicMock()
        mock_workflow.get_step = MagicMock(return_value=mock_step)

        mock_state = WorkflowState(
            session_id="sess-test",
            workflow_name="test-workflow",
            step="execute",
            variables={},
        )
        runner._workflow_state_manager.get_state = MagicMock(return_value=mock_state)
        runner._workflow_state_manager.save_state = MagicMock()

        async def base_handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(tool_name=tool_name, success=True, result="OK")

        handler = runner._create_workflow_filtered_handler(
            base_handler=base_handler,
            session_id="sess-test",
            workflow_definition=mock_workflow,
        )

        result = await handler("complete", {"result": "Task finished successfully"})

        assert result.success is True
        assert result.result["status"] == "completed"
        assert result.result["message"] == "Task finished successfully"
        # Verify workflow state was updated
        runner._workflow_state_manager.save_state.assert_called_once()
        saved_state = runner._workflow_state_manager.save_state.call_args[0][0]
        assert saved_state.variables["workflow_completed"] is True
