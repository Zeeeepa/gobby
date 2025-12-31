from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.actions import ActionExecutor
from gobby.workflows.definitions import WorkflowDefinition, WorkflowPhase, WorkflowState
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

        # Setup workflow with reflect phase
        workflow = MagicMock(spec=WorkflowDefinition)

        # side_effect for get_phase
        def get_phase_side_effect(name):
            if name in ["working", "reflect"]:
                return MagicMock()
            return None

        workflow.get_phase.side_effect = get_phase_side_effect
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
        assert "Phase duration limit exceeded" in response.context
        assert state.phase == "reflect"  # Transited

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

        phase1 = MagicMock(spec=WorkflowPhase)
        phase1.blocked_tools = ["forbidden_tool"]
        phase1.allowed_tools = "all"
        phase1.rules = []
        phase1.transitions = []
        phase1.exit_conditions = []

        workflow = MagicMock(spec=WorkflowDefinition)
        workflow.get_phase.return_value = phase1
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
        assert "blocked in phase" in response.reason

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
