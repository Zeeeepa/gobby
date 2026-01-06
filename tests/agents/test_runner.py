"""Tests for AgentRunner and AgentRunContext."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.agents.runner import AgentConfig, AgentRunContext, AgentRunner, RunningAgent
from gobby.llm.executor import AgentResult


class TestAgentRunContext:
    """Tests for AgentRunContext dataclass."""

    def test_default_values(self):
        """All fields default to None."""
        ctx = AgentRunContext()

        assert ctx.session is None
        assert ctx.run is None
        assert ctx.workflow_state is None
        assert ctx.workflow_config is None

    def test_session_id_property(self):
        """session_id property returns session.id."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"

        ctx = AgentRunContext(session=mock_session)

        assert ctx.session_id == "sess-123"

    def test_session_id_none_when_no_session(self):
        """session_id returns None when session is None."""
        ctx = AgentRunContext()

        assert ctx.session_id is None

    def test_run_id_property(self):
        """run_id property returns run.id."""
        mock_run = MagicMock()
        mock_run.id = "run-456"

        ctx = AgentRunContext(run=mock_run)

        assert ctx.run_id == "run-456"

    def test_run_id_none_when_no_run(self):
        """run_id returns None when run is None."""
        ctx = AgentRunContext()

        assert ctx.run_id is None

    def test_all_fields_settable(self):
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

    def test_prompt_required(self):
        """prompt is the only required field."""
        config = AgentConfig(prompt="Do something")

        assert config.prompt == "Do something"

    def test_default_values(self):
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

    def test_get_effective_workflow_prefers_workflow(self):
        """get_effective_workflow prefers 'workflow' over 'workflow_name'."""
        config = AgentConfig(
            prompt="test",
            workflow="new-workflow",
            workflow_name="old-workflow",
        )

        assert config.get_effective_workflow() == "new-workflow"

    def test_get_effective_workflow_fallback(self):
        """get_effective_workflow falls back to workflow_name."""
        config = AgentConfig(
            prompt="test",
            workflow_name="legacy-workflow",
        )

        assert config.get_effective_workflow() == "legacy-workflow"

    def test_get_effective_workflow_none(self):
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

    def test_prepare_run_validates_parent_session_id(self, runner):
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

    def test_prepare_run_validates_project_id(self, runner):
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

    def test_prepare_run_validates_machine_id(self, runner):
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

    def test_prepare_run_creates_context(self, runner, mock_session_storage):
        """prepare_run creates AgentRunContext with session and run."""
        # Mock can_spawn to allow spawning
        runner._child_session_manager.can_spawn_child = MagicMock(
            return_value=(True, "OK", 0)
        )

        # Mock the child session manager to return a session
        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(
            return_value=child_session
        )

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

    def test_prepare_run_checks_spawn_depth(self, runner):
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
        runner._child_session_manager.can_spawn_child = MagicMock(
            return_value=(True, "OK", 0)
        )

        # Setup child session manager
        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(
            return_value=child_session
        )

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
        runner._child_session_manager.can_spawn_child = MagicMock(
            return_value=(True, "OK", 0)
        )

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(
            return_value=child_session
        )

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

    def test_prepare_run_sets_terminal_pickup_metadata(self, runner, mock_session_storage):
        """prepare_run calls update_terminal_pickup_metadata with correct values."""
        # Mock can_spawn to allow spawning
        runner._child_session_manager.can_spawn_child = MagicMock(
            return_value=(True, "OK", 0)
        )

        # Mock the child session manager to return a session
        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(
            return_value=child_session
        )

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

    def test_prepare_run_sets_metadata_without_workflow(self, runner, mock_session_storage):
        """prepare_run sets metadata even when no workflow specified."""
        runner._child_session_manager.can_spawn_child = MagicMock(
            return_value=(True, "OK", 0)
        )

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(
            return_value=child_session
        )

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

    def test_prepare_run_uses_legacy_workflow_name(self, runner, mock_session_storage):
        """prepare_run uses legacy workflow_name if workflow not specified."""
        runner._child_session_manager.can_spawn_child = MagicMock(
            return_value=(True, "OK", 0)
        )

        child_session = MagicMock()
        child_session.id = "sess-child"
        child_session.agent_depth = 1
        runner._child_session_manager.create_child_session = MagicMock(
            return_value=child_session
        )

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
    """Tests for RunningAgent dataclass."""

    def test_create_running_agent(self):
        """RunningAgent stores all fields correctly."""
        now = datetime.now()
        agent = RunningAgent(
            run_id="run-123",
            parent_session_id="sess-parent",
            child_session_id="sess-child",
            provider="claude",
            prompt="Test prompt",
            started_at=now,
            workflow_name="plan-execute",
            model="opus",
            worktree_id="wt-abc",
            mode="terminal",
            pid=12345,
        )

        assert agent.run_id == "run-123"
        assert agent.parent_session_id == "sess-parent"
        assert agent.child_session_id == "sess-child"
        assert agent.provider == "claude"
        assert agent.prompt == "Test prompt"
        assert agent.started_at == now
        assert agent.workflow_name == "plan-execute"
        assert agent.model == "opus"
        assert agent.worktree_id == "wt-abc"
        assert agent.mode == "terminal"
        assert agent.pid == 12345

    def test_running_agent_defaults(self):
        """RunningAgent has correct default values."""
        agent = RunningAgent(
            run_id="run-1",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="gemini",
            prompt="Task",
            started_at=datetime.now(),
        )

        assert agent.workflow_name is None
        assert agent.model is None
        assert agent.worktree_id is None
        assert agent.mode == "in_process"
        assert agent.turns_used == 0
        assert agent.tool_calls_count == 0
        assert agent.pid is None

    def test_to_dict(self):
        """RunningAgent.to_dict() returns correct dict."""
        now = datetime.now()
        agent = RunningAgent(
            run_id="run-abc",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="claude",
            prompt="Short prompt",
            started_at=now,
            mode="headless",
        )

        result = agent.to_dict()

        assert result["run_id"] == "run-abc"
        assert result["parent_session_id"] == "sess-p"
        assert result["child_session_id"] == "sess-c"
        assert result["provider"] == "claude"
        assert result["prompt"] == "Short prompt"
        assert result["started_at"] == now.isoformat()
        assert result["mode"] == "headless"

    def test_to_dict_truncates_long_prompt(self):
        """RunningAgent.to_dict() truncates prompts over 100 chars."""
        long_prompt = "x" * 150
        agent = RunningAgent(
            run_id="run-1",
            parent_session_id="sess-p",
            child_session_id="sess-c",
            provider="claude",
            prompt=long_prompt,
            started_at=datetime.now(),
        )

        result = agent.to_dict()

        assert len(result["prompt"]) == 103  # 100 + "..."
        assert result["prompt"].endswith("...")


class TestAgentRunnerInMemoryTracking:
    """Tests for AgentRunner in-memory running agents tracking."""

    def test_track_running_agent(self, runner):
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

    def test_untrack_running_agent(self, runner):
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

    def test_untrack_nonexistent_returns_none(self, runner):
        """_untrack_running_agent returns None for missing agent."""
        result = runner._untrack_running_agent("nonexistent-run")

        assert result is None

    def test_update_running_agent(self, runner):
        """_update_running_agent updates agent state."""
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

        assert updated is not None
        assert updated.turns_used == 5
        assert updated.tool_calls_count == 10

    def test_get_running_agent(self, runner):
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

    def test_get_running_agent_not_found(self, runner):
        """get_running_agent returns None for missing agent."""
        agent = runner.get_running_agent("missing")

        assert agent is None

    def test_get_running_agents(self, runner):
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

    def test_get_running_agents_filter_by_parent(self, runner):
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

    def test_get_running_agents_count(self, runner):
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

    def test_is_agent_running(self, runner):
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
