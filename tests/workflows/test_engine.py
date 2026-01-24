from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.actions import ActionExecutor
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState, WorkflowStep
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager


@pytest.fixture
def mock_loader():
    loader = MagicMock(spec=WorkflowLoader)
    return loader


@pytest.fixture
def mock_state_manager():
    manager = MagicMock(spec=WorkflowStateManager)
    return manager


@pytest.fixture
def mock_action_executor():
    executor = AsyncMock(spec=ActionExecutor)
    executor.db = MagicMock()
    executor.session_manager = MagicMock()
    executor.template_engine = MagicMock()
    executor.llm_service = MagicMock()
    executor.transcript_processor = MagicMock()
    executor.config = MagicMock()
    executor.mcp_manager = MagicMock()
    executor.memory_manager = MagicMock()
    executor.memory_sync_manager = MagicMock()
    executor.session_task_manager = MagicMock()
    executor.task_sync_manager = MagicMock()
    return executor


@pytest.fixture
def workflow_engine(mock_loader, mock_state_manager, mock_action_executor):
    return WorkflowEngine(mock_loader, mock_state_manager, mock_action_executor)


@pytest.mark.asyncio
class TestWorkflowEngine:
    async def test_handle_event_no_session(self, workflow_engine):
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )
        response = await workflow_engine.handle_event(event)
        assert response.decision == "allow"

    async def test_handle_event_no_state_and_no_workflow(self, workflow_engine, mock_state_manager):
        mock_state_manager.get_state.return_value = None
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        response = await workflow_engine.handle_event(event)
        assert response.decision == "allow"

    async def test_handle_event_stuck_prevention(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        # Setup stuck state using REAL object
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="working",
            step_entered_at=datetime.now(UTC) - timedelta(minutes=60),
            step_action_count=0,
            total_action_count=100,
        )

        mock_state_manager.get_state.return_value = state

        # Setup workflow with reflect step
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        # side_effect for get_step
        def get_step_side_effect(name):
            if name in ["working", "reflect"]:
                return MagicMock()
            return None

        workflow.get_step.side_effect = get_step_side_effect
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "modify"
        assert "Step duration limit exceeded" in response.context
        assert state.step == "reflect"  # Transited

    async def test_handle_event_tool_blocked(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        # Use real state
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = ["forbidden_tool"]
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "forbidden_tool"},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "blocked in step" in response.reason

    async def test_evaluate_lifecycle_triggers_execution(
        self, workflow_engine, mock_loader, mock_action_executor
    ):
        # Setup lifecycle workflow
        trigger = {"action": "test_action", "arg1": "val1"}
        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "lifecycle"
        workflow.triggers = {"on_session_start": [trigger]}
        workflow.name = "lifecycle_wf"

        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        # Mock action execution result
        mock_action_executor.execute.return_value = {"key": "value"}

        response = await workflow_engine.evaluate_lifecycle_triggers("lifecycle_wf", event)

        assert response.decision == "allow"
        mock_action_executor.execute.assert_called()
        args, kwargs = mock_action_executor.execute.call_args
        assert args[0] == "test_action"
        assert kwargs["arg1"] == "val1"

    async def test_handle_event_tool_allowed_in_list(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Tool is allowed when in the allowed_tools list."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = ["Read", "Glob", "Grep"]  # Specific list
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "Read"},  # In allowed list
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"

    async def test_handle_event_tool_not_in_allowed_list(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Tool is blocked when not in the allowed_tools list."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = ["Read", "Glob", "Grep"]  # Specific list
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "Edit"},  # Not in allowed list
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "not in allowed list" in response.reason

    async def test_handle_event_tool_blocked_while_approval_pending(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Tools are blocked while waiting for user approval."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            approval_pending=True,
            approval_condition_id="test_approval",
            approval_prompt="Ready to proceed?",
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "Read"},  # Normally allowed
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "approval" in response.reason.lower()

    async def test_handle_event_disabled_workflow_allows_all(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Disabled workflow allows all tools (escape hatch)."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            disabled=True,
            disabled_reason="Testing escape hatch",
        )
        mock_state_manager.get_state.return_value = state

        # Don't even need to set up the workflow since disabled returns early
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "any_tool"},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"

    async def test_handle_event_tool_allowed_all(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Tool is allowed when allowed_tools is 'all'."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "any_tool"},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"

    async def test_handle_event_blocked_list_takes_precedence(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Blocked tools list takes precedence over allowed_tools='all'."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = ["Bash", "Edit", "Write"]  # Dangerous tools
        step1.allowed_tools = "all"  # All others allowed
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "Bash"},  # In blocked list
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "blocked in step" in response.reason


@pytest.mark.asyncio
class TestDetectTaskClaim:
    """Tests for AFTER_TOOL detection of gobby-tasks calls."""

    async def test_create_task_sets_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Successful create_task sets task_claimed=True."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "create_task",
                    "arguments": {"title": "Test task"},
                },
                "tool_output": {"status": "success", "result": {"id": "gt-123"}},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is True
        mock_state_manager.save_state.assert_called()

    async def test_update_task_in_progress_sets_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """update_task with status=in_progress sets task_claimed=True."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "call_tool",  # Alternative tool name
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "update_task",
                    "arguments": {"task_id": "gt-123", "status": "in_progress"},
                },
                "tool_output": {"status": "success"},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is True

    async def test_claim_task_sets_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """claim_task sets task_claimed=True."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "claim_task",
                    "arguments": {"task_id": "#123", "session_id": "sess1"},
                },
                "tool_output": {"status": "success"},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is True
        assert state.variables.get("claimed_task_id") == "#123"

    async def test_update_task_without_status_change_does_not_set_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """update_task without status=in_progress does NOT set task_claimed."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "update_task",
                    "arguments": {"task_id": "gt-123", "priority": 1},  # No status
                },
                "tool_output": {"status": "success"},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is None

    async def test_list_tasks_does_not_set_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Read-only operations like list_tasks do NOT set task_claimed."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "list_tasks",
                    "arguments": {},
                },
                "tool_output": {"status": "success", "result": {"tasks": []}},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is None

    async def test_failed_create_task_does_not_set_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Failed create_task does NOT set task_claimed."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "create_task",
                    "arguments": {"title": "Test task"},
                },
                "tool_output": {"error": "Database error"},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is None

    async def test_non_gobby_tasks_server_does_not_set_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Calls to other servers do NOT set task_claimed."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "tool_input": {
                    "server_name": "gobby-memory",  # Different server
                    "tool_name": "create_memory",
                    "arguments": {"content": "test"},
                },
                "tool_output": {"status": "success"},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is None

    async def test_other_tool_does_not_set_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Non-MCP tools do NOT set task_claimed."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "Read",  # Not an MCP call_tool
                "tool_input": {"file_path": "/path/to/file"},
                "tool_output": {"content": "file content"},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is None

    async def test_error_status_does_not_set_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """MCP error status does NOT set task_claimed."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "create_task",
                    "arguments": {"title": "Test task"},
                },
                "tool_output": {"status": "error", "message": "Failed"},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is None
