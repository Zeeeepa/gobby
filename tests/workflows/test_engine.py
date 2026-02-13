from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState, WorkflowStep
from gobby.workflows.engine import TransitionResult, WorkflowEngine
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

pytestmark = pytest.mark.unit


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
    executor = AsyncMock()
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
    executor.pipeline_executor = MagicMock()
    executor.task_manager = MagicMock()
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
        step1.on_enter = []
        step1.blocked_tools = ["forbidden_tool"]
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = ["Read", "Glob", "Grep"]  # Specific list
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = ["Read", "Glob", "Grep"]  # Specific list
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = ["Bash", "Edit", "Write"]  # Dangerous tools
        step1.allowed_tools = "all"  # All others allowed
        step1.rules = []
        step1.check_rules = []
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

    async def test_handle_event_mcp_tool_blocked(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """MCP tool is blocked when in blocked_mcp_tools list."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.blocked_mcp_tools = ["gobby-tasks:list_tasks", "gobby-tasks:create_task"]
        step1.allowed_mcp_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
            data={
                "tool_name": "mcp__gobby__call_tool",
                "mcp_server": "gobby-tasks",
                "mcp_tool": "list_tasks",
            },
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "gobby-tasks:list_tasks" in response.reason
        assert "blocked in step" in response.reason

    async def test_handle_event_mcp_tool_not_in_allowed_list(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """MCP tool is blocked when not in allowed_mcp_tools list."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.blocked_mcp_tools = []
        step1.allowed_mcp_tools = ["gobby-tasks:claim_task", "gobby-tasks:get_task"]
        step1.rules = []
        step1.check_rules = []
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
            data={
                "tool_name": "mcp__gobby__call_tool",
                "mcp_server": "gobby-tasks",
                "mcp_tool": "list_tasks",  # Not in allowed list
            },
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "gobby-tasks:list_tasks" in response.reason
        assert "not in allowed list" in response.reason

    async def test_handle_event_mcp_tool_allowed_when_in_list(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """MCP tool is allowed when in allowed_mcp_tools list."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.blocked_mcp_tools = []
        step1.allowed_mcp_tools = ["gobby-tasks:claim_task", "gobby-tasks:get_task"]
        step1.rules = []
        step1.check_rules = []
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
            data={
                "tool_name": "mcp__gobby__call_tool",
                "mcp_server": "gobby-tasks",
                "mcp_tool": "claim_task",  # In allowed list
            },
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"

    async def test_handle_event_mcp_tool_wildcard_block(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """MCP tools are blocked by wildcard pattern (server:*)."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.blocked_mcp_tools = ["gobby-workflows:*"]  # Block all workflow tools
        step1.allowed_mcp_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
            data={
                "tool_name": "mcp__gobby__call_tool",
                "mcp_server": "gobby-workflows",
                "mcp_tool": "end_workflow",
            },
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "gobby-workflows:end_workflow" in response.reason


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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
                "mcp_server": "gobby-tasks",
                "mcp_tool": "create_task",
                "tool_input": {
                    "server_name": "gobby-tasks",
                    "tool_name": "create_task",
                    "arguments": {"title": "Test task"},
                },
                "tool_output": {"status": "success", "result": {"id": "gt-123"}},
            },
            metadata={"_platform_session_id": "sess1"},
        )

        # Ensure task manager doesn't interfere
        mock_action_executor.task_manager = MagicMock()

        await workflow_engine.handle_event(event)

        assert state.variables.get("task_claimed") is True
        mock_state_manager.save_state.assert_called()

    async def test_update_task_in_progress_sets_task_claimed(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
                "mcp_server": "gobby-tasks",  # Normalized MCP fields
                "mcp_tool": "update_task",
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
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        # Mock task manager to return a task with the expected UUID
        task = MagicMock()
        task.id = "task-uuid-123"
        mock_action_executor.task_manager.get_task.return_value = task

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={
                "tool_name": "mcp__gobby__call_tool",
                "mcp_server": "gobby-tasks",  # Normalized MCP fields
                "mcp_tool": "claim_task",
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
        assert state.variables.get("claimed_task_id") == "task-uuid-123"
        mock_state_manager.save_state.assert_called()

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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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

    async def test_transition_to_sets_context_injected(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """transition_to sets context_injected=True when on_enter produces messages."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = [{"action": "inject_message", "content": "Hello"}]

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        # Mock the execute to return inject_message
        mock_action_executor.execute.return_value = {"inject_message": "Hello"}

        result = await workflow_engine.transition_to(state, "step2", workflow)

        assert state.step == "step2"
        assert state.context_injected is True
        assert result.injected_messages == ["Hello"]
        assert result.system_messages == []  # No status_message on mock step
        # save_state should have been called multiple times (once for state update, once for context_injected)
        assert mock_state_manager.save_state.call_count >= 2

    async def test_transition_to_no_context_injected_when_no_messages(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """transition_to does NOT set context_injected when on_enter produces no messages."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = [{"action": "set_variable", "name": "x", "value": 1}]

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        # Mock execute returns a result without inject_message
        mock_action_executor.execute.return_value = {"variable_set": "x", "value": 1}

        result = await workflow_engine.transition_to(state, "step2", workflow)

        assert state.step == "step2"
        assert state.context_injected is False  # No messages, so stays False
        assert result.injected_messages == []
        assert result.system_messages == []

    async def test_auto_transition_chain_follows_transitions(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """Auto-transition chain follows transitions when on_enter sets satisfying variables."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step_a",
            step_entered_at=datetime.now(UTC),
            variables={"ready": True},
        )

        step_a = MagicMock(spec=WorkflowStep)
        step_a.on_enter = []
        step_a.on_exit = []
        step_a.transitions = [MagicMock(when="ready", to="step_b", on_transition=None)]

        step_b = MagicMock(spec=WorkflowStep)
        step_b.on_enter = [{"action": "inject_message", "content": "In step B"}]
        step_b.on_exit = []
        step_b.transitions = []  # No further transitions

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step_a": step_a, "step_b": step_b}.get(name)

        workflow.get_step.side_effect = get_step

        mock_action_executor.execute.return_value = {"inject_message": "In step B"}

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        result = await workflow_engine._auto_transition_chain(
            state,
            workflow,
            {},
            {},
            event,
            TransitionResult(injected_messages=["Initial message"]),
        )

        assert state.step == "step_b"
        assert "Initial message" in result.injected_messages
        assert "In step B" in result.injected_messages

    async def test_auto_transition_chain_respects_max_depth(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """Auto-transition chain stops at max_depth to prevent infinite loops."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="loop_step",
            step_entered_at=datetime.now(UTC),
            variables={"looping": True},
        )

        # Create a step that always transitions back to itself
        loop_step = MagicMock(spec=WorkflowStep)
        loop_step.on_enter = []
        loop_step.on_exit = []
        loop_step.transitions = [MagicMock(when="looping", to="loop_step", on_transition=None)]

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.name = "default"
        workflow.type = "step"
        workflow.get_step.return_value = loop_step

        mock_action_executor.execute.return_value = None

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        # Should stop after max_depth=3 iterations
        await workflow_engine._auto_transition_chain(
            state,
            workflow,
            {},
            {},
            event,
            TransitionResult(),
            max_depth=3,
        )

        # The step should still be loop_step (it transitions to itself)
        assert state.step == "loop_step"
        # transition_to should have been called exactly 3 times
        assert mock_state_manager.save_state.call_count == 3

    async def test_auto_transition_chain_stops_when_no_transition_matches(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """Auto-transition chain stops when no transition condition is satisfied."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="wait_step",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

        wait_step = MagicMock(spec=WorkflowStep)
        wait_step.on_enter = []
        wait_step.transitions = [MagicMock(when="completed", to="done")]

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.get_step.return_value = wait_step

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        result = await workflow_engine._auto_transition_chain(
            state,
            workflow,
            {},
            {},
            event,
            TransitionResult(injected_messages=["initial"]),
        )

        # No transition matched, state unchanged
        assert state.step == "wait_step"
        assert result.injected_messages == ["initial"]

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
        step1.on_enter = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.rules = []
        step1.check_rules = []
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


@pytest.mark.asyncio
class TestConditionalActions:
    """Tests for `when` conditional support on on_enter actions."""

    async def test_action_skipped_when_condition_false(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """Actions with a false `when` condition are skipped."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={"should_run": False},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = [
            {"action": "inject_message", "content": "Always runs"},
            {"action": "inject_message", "content": "Conditional", "when": "variables.get('should_run')"},
        ]

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        mock_action_executor.execute.return_value = {"inject_message": "Always runs"}

        result = await workflow_engine.transition_to(state, "step2", workflow)

        assert state.step == "step2"
        # Only the unconditional action should have executed
        assert mock_action_executor.execute.call_count == 1
        assert result.injected_messages == ["Always runs"]

    async def test_action_runs_when_condition_true(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """Actions with a true `when` condition are executed."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={"should_run": True},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = [
            {"action": "set_variable", "name": "x", "value": 1},
            {"action": "inject_message", "content": "Conditional", "when": "variables.get('should_run')"},
        ]

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        mock_action_executor.execute.side_effect = [
            {"variable_set": "x", "value": 1},
            {"inject_message": "Conditional"},
        ]

        result = await workflow_engine.transition_to(state, "step2", workflow)

        assert state.step == "step2"
        # Both actions should have executed
        assert mock_action_executor.execute.call_count == 2
        assert result.injected_messages == ["Conditional"]

    async def test_action_without_when_always_runs(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """Actions without a `when` field always execute (backward compatible)."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = [
            {"action": "set_variable", "name": "x", "value": 1},
            {"action": "inject_message", "content": "Hello"},
        ]

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        mock_action_executor.execute.side_effect = [
            {"variable_set": "x", "value": 1},
            {"inject_message": "Hello"},
        ]

        result = await workflow_engine.transition_to(state, "step2", workflow)

        assert mock_action_executor.execute.call_count == 2
        assert result.injected_messages == ["Hello"]


@pytest.mark.asyncio
class TestStatusMessage:
    """Tests for status_message rendering on workflow step transitions."""

    async def test_status_message_rendered_on_transition(
        self, workflow_engine, mock_state_manager, mock_action_executor
    ) -> None:
        """status_message is rendered and returned in TransitionResult.system_messages."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={"task_id": "#42"},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = []
        step2.status_message = "Working on task {{ variables.task_id }}"

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        # Template engine renders the template
        mock_action_executor.template_engine.render.return_value = "Working on task #42"

        result = await workflow_engine.transition_to(state, "step2", workflow)

        assert result.system_messages == ["Working on task #42"]
        mock_action_executor.template_engine.render.assert_called_once_with(
            "Working on task {{ variables.task_id }}",
            {"variables": state.variables, "state": state, "session_id": "sess1"},
        )

    async def test_no_status_message_when_not_defined(
        self, workflow_engine, mock_state_manager, mock_action_executor
    ) -> None:
        """Steps without status_message produce empty system_messages."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = []
        step2.status_message = None

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        result = await workflow_engine.transition_to(state, "step2", workflow)

        assert result.system_messages == []

    async def test_status_message_survives_render_error(
        self, workflow_engine, mock_state_manager, mock_action_executor
    ) -> None:
        """Template render failure logs warning and returns empty system_messages."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_exit = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = []
        step2.status_message = "{{ bad_template }}"
        step2.name = "step2"

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step

        mock_action_executor.template_engine.render.side_effect = Exception("Template error")

        result = await workflow_engine.transition_to(state, "step2", workflow)

        # Transition still succeeds, just no system_message
        assert state.step == "step2"
        assert result.system_messages == []

    async def test_auto_chain_accumulates_system_messages(
        self, workflow_engine, mock_state_manager, mock_action_executor
    ) -> None:
        """Auto-transition chain accumulates system_messages from multiple steps."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step_a",
            step_entered_at=datetime.now(UTC),
            variables={"ready": True},
        )

        step_a = MagicMock(spec=WorkflowStep)
        step_a.on_enter = []
        step_a.on_exit = []
        step_a.status_message = None
        step_a.transitions = [MagicMock(when="ready", to="step_b", on_transition=None)]

        step_b = MagicMock(spec=WorkflowStep)
        step_b.on_enter = []
        step_b.on_exit = []
        step_b.status_message = "Entered step B"
        step_b.transitions = [MagicMock(when="ready", to="step_c", on_transition=None)]

        step_c = MagicMock(spec=WorkflowStep)
        step_c.on_enter = []
        step_c.on_exit = []
        step_c.status_message = "Entered step C"
        step_c.transitions = []  # Terminal step

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.name = "test"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step_a": step_a, "step_b": step_b, "step_c": step_c}.get(name)

        workflow.get_step.side_effect = get_step

        mock_action_executor.execute.return_value = None
        mock_action_executor.template_engine.render.side_effect = lambda tmpl, ctx: tmpl

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        result = await workflow_engine._auto_transition_chain(
            state,
            workflow,
            {},
            {},
            event,
            TransitionResult(system_messages=["Entered step A"]),
        )

        assert state.step == "step_c"
        assert result.system_messages == ["Entered step A", "Entered step B", "Entered step C"]

    async def test_handle_event_sets_system_message_on_transition(
        self, workflow_engine, mock_state_manager, mock_loader, mock_action_executor
    ) -> None:
        """handle_event returns HookResponse with system_message from status_message."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="step1",
            step_entered_at=datetime.now(UTC),
            step_action_count=1,
            total_action_count=1,
            variables={"go": True},
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.on_enter = []
        step1.on_exit = []
        step1.blocked_tools = []
        step1.allowed_tools = "all"
        step1.allowed_mcp_tools = "all"
        step1.blocked_mcp_tools = []
        step1.rules = []
        step1.exit_conditions = []
        step1.status_message = None
        step1.transitions = [MagicMock(when="go", to="step2", on_transition=None)]

        step1.on_mcp_success = []
        step1.on_mcp_error = []

        step2 = MagicMock(spec=WorkflowStep)
        step2.on_enter = [{"action": "inject_message", "content": "In step 2"}]
        step2.on_exit = []
        step2.status_message = "Now in step 2"
        step2.transitions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.type = "step"
        workflow.name = "default"

        def get_step(name: str) -> WorkflowStep | None:
            return {"step1": step1, "step2": step2}.get(name)

        workflow.get_step.side_effect = get_step
        mock_loader.load_workflow.return_value = workflow

        mock_action_executor.execute.return_value = {"inject_message": "In step 2"}
        mock_action_executor.template_engine.render.return_value = "Now in step 2"
        mock_action_executor.session_manager = MagicMock()

        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "Read", "tool_input": {}, "tool_output": {}},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "modify"
        assert response.system_message == "Now in step 2"
        assert "In step 2" in response.context
