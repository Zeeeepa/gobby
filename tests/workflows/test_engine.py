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
    executor.skill_learner = MagicMock()
    executor.memory_sync_manager = MagicMock()
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
            phase="working",
            phase_entered_at=datetime.now(UTC) - timedelta(minutes=60),
            phase_action_count=0,
            total_action_count=100,
        )

        mock_state_manager.get_state.return_value = state

        # Setup workflow with reflect step
        workflow = MagicMock(spec=WorkflowDefinition)

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
            phase="phase1",
            phase_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = ["forbidden_tool"]
        step1.allowed_tools = "all"
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.tool_name = "forbidden_tool"

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "blocked in step" in response.reason

    async def test_evaluate_lifecycle_triggers_execution(
        self, workflow_engine, mock_loader, mock_action_executor
    ):
        # Setup lifecycle workflow
        trigger = {"action": "test_action", "arg1": "val1"}
        workflow = MagicMock(spec=WorkflowDefinition)
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
            phase="phase1",
            phase_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = ["Read", "Glob", "Grep"]  # Specific list
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.tool_name = "Read"  # In allowed list

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"

    async def test_handle_event_tool_not_in_allowed_list(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Tool is blocked when not in the allowed_tools list."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            phase="phase1",
            phase_entered_at=datetime.now(UTC),
        )
        mock_state_manager.get_state.return_value = state

        step1 = MagicMock(spec=WorkflowStep)
        step1.blocked_tools = []
        step1.allowed_tools = ["Read", "Glob", "Grep"]  # Specific list
        step1.rules = []
        step1.transitions = []
        step1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.tool_name = "Edit"  # Not in allowed list

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
            phase="phase1",
            phase_entered_at=datetime.now(UTC),
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
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.tool_name = "Read"  # Normally allowed

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
            phase="phase1",
            phase_entered_at=datetime.now(UTC),
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
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.tool_name = "any_tool"

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"

    async def test_handle_event_tool_allowed_all(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Tool is allowed when allowed_tools is 'all'."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="phase1",
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
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.tool_name = "any_tool"

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"

    async def test_handle_event_blocked_list_takes_precedence(
        self, workflow_engine, mock_state_manager, mock_loader
    ):
        """Blocked tools list takes precedence over allowed_tools='all'."""
        state = WorkflowState(
            session_id="sess1",
            workflow_name="default",
            step="phase1",
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
        workflow.get_step.return_value = step1
        mock_loader.load_workflow.return_value = workflow

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.tool_name = "Bash"  # In blocked list

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "blocked in step" in response.reason
