from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.storage.workflow_audit import WorkflowAuditManager
from gobby.workflows.actions import ActionExecutor
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState, WorkflowStep
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_loader():
    loader = MagicMock(spec=WorkflowLoader)
    loader.discover_workflows = AsyncMock(return_value=[])
    return loader


@pytest.fixture
def mock_state_manager():
    return MagicMock(spec=WorkflowStateManager)


@pytest.fixture
def mock_action_executor():
    executor = AsyncMock(spec=ActionExecutor)
    # Setup nested mocks for action context creation
    executor.db = MagicMock()
    executor.session_manager = MagicMock()
    executor.template_engine = MagicMock()
    executor.llm_service = MagicMock()
    executor.transcript_processor = MagicMock()
    executor.config = MagicMock()
    executor.tool_proxy_getter = MagicMock()
    executor.memory_manager = MagicMock()
    executor.memory_sync_manager = MagicMock()
    executor.session_task_manager = MagicMock()
    executor.task_manager = MagicMock()
    executor.task_sync_manager = MagicMock()
    executor.skill_manager = MagicMock()
    executor.pipeline_executor = MagicMock()
    executor.workflow_loader = MagicMock()
    return executor


@pytest.fixture
def mock_evaluator():
    return MagicMock(spec=ConditionEvaluator)


@pytest.fixture
def mock_audit_manager():
    return MagicMock(spec=WorkflowAuditManager)


@pytest.fixture
def workflow_engine(
    mock_loader, mock_state_manager, mock_action_executor, mock_evaluator, mock_audit_manager
):
    return WorkflowEngine(
        mock_loader,
        mock_state_manager,
        mock_action_executor,
        evaluator=mock_evaluator,
        audit_manager=mock_audit_manager,
    )


@pytest.mark.asyncio
class TestWorkflowEngineExtended:
    async def test_handle_approval_response_approved(self, workflow_engine, mock_state_manager):
        # Setup state waiting for approval
        state = WorkflowState(
            session_id="sess1",
            workflow_name="test_wf",
            step="working",
            step_entered_at=datetime.now(UTC),
            approval_pending=True,
            approval_condition_id="cond1",
            approval_prompt="Continue?",
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        # Setup event with "yes"
        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"prompt": "yes, please proceed"},
            metadata={"_platform_session_id": "sess1"},
        )

        # Need real WorkflowDefinition for isinstance check in handle_event
        working_step = WorkflowStep(name="working")
        wf = WorkflowDefinition(name="test_wf", steps=[working_step])
        workflow_engine.loader.load_workflow.return_value = wf

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"
        assert state.approval_pending is False
        assert state.variables["_approval_cond1_granted"] is True
        mock_state_manager.save_state.assert_called_with(state)

    async def test_handle_approval_response_rejected(self, workflow_engine, mock_state_manager):
        state = WorkflowState(
            session_id="sess1",
            workflow_name="test_wf",
            step="working",
            step_entered_at=datetime.now(UTC),
            approval_pending=True,
            approval_condition_id="cond1",
            approval_prompt="Continue?",
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"prompt": "no, stop"},
            metadata={"_platform_session_id": "sess1"},
        )

        working_step = WorkflowStep(name="working")
        wf = WorkflowDefinition(name="test_wf", steps=[working_step])
        workflow_engine.loader.load_workflow.return_value = wf

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert state.approval_pending is False
        assert state.variables["_approval_cond1_rejected"] is True

    async def test_handle_approval_response_timeout(
        self, workflow_engine, mock_state_manager, mock_evaluator
    ):
        # To hit the timeout logic in _handle_approval_response, we must be processing BEFORE_AGENT
        state = WorkflowState(
            session_id="sess1",
            workflow_name="test_wf",
            step="working",
            step_entered_at=datetime.now(UTC),
            approval_pending=False,
            variables={},
        )
        mock_state_manager.get_state.return_value = state

        working_step = WorkflowStep(name="working")
        wf = WorkflowDefinition(name="test_wf", steps=[working_step])
        workflow_engine.loader.load_workflow.return_value = wf

        # Mock evaluator to return a TIMED OUT result
        mock_result = MagicMock()
        mock_result.needs_approval = False
        mock_result.is_timed_out = True
        mock_result.condition_id = "cond_timeout"
        mock_result.timeout_seconds = 60
        mock_evaluator.check_pending_approval.return_value = mock_result

        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,  # Changed from BEFORE_TOOL
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"prompt": "hello"},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "block"
        assert "timed out" in response.reason
        assert state.variables["_approval_cond_timeout_rejected"] is True

    async def test_audit_logging_failure(self, workflow_engine, mock_audit_manager):
        # Force exception in audit logging
        mock_audit_manager.log_tool_call.side_effect = Exception("Audit Error")

        # Should not raise exception
        workflow_engine._log_tool_call("sess", "step", "tool", "allow")

    async def test_audit_logging_methods(self, workflow_engine, mock_audit_manager):
        # Cover exception blocks in log helper methods
        mock_audit_manager.log_rule_eval.side_effect = Exception("Audit Error")
        workflow_engine._log_rule_eval("s", "p", "r", "c", "res")

        mock_audit_manager.log_transition.side_effect = Exception("Audit Error")
        workflow_engine._log_transition("s", "p", "p2")

    async def test_request_approval_logic(
        self, workflow_engine, mock_state_manager, mock_evaluator
    ):
        # Test path where Approval is requested (needs_approval=True)
        state = WorkflowState(
            session_id="sess1",
            workflow_name="wf",
            step="working",
            step_entered_at=datetime.now(UTC),
            approval_pending=False,
        )
        mock_state_manager.get_state.return_value = state

        working_step = WorkflowStep(name="working", exit_conditions=[{"type": "approval"}])
        wf = WorkflowDefinition(name="wf", steps=[working_step])
        workflow_engine.loader.load_workflow.return_value = wf

        # Evaluator returns needs_approval
        check = MagicMock()
        check.needs_approval = True
        check.condition_id = "cond1"
        check.prompt = "Confirm?"
        check.timeout_seconds = 60
        mock_evaluator.check_pending_approval.return_value = check

        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.handle_event(event)

        assert response.decision == "allow"
        assert "Approval Required" in response.context
        assert state.approval_pending is True
        assert state.approval_condition_id == "cond1"

    async def test_transition_failure(self, workflow_engine, mock_state_manager):
        # Test transition to unknown step
        state = WorkflowState(
            session_id="sess1",
            workflow_name="wf",
            step="step1",
            step_entered_at=datetime.now(UTC),
        )
        wf = MagicMock()
        wf.get_step.return_value = None  # New step unknown

        await workflow_engine.transition_to(state, "unknown_step", wf)
        # Should log error and return
        assert state.step == "step1"

    async def test_audit_logging_calls(self, workflow_engine, mock_audit_manager):
        # We want to ensure _log_tool_call, _log_transition, etc are called.
        # They are called during transitions and tool checks.

        # Setup a simple allow tool flow
        state = WorkflowState(
            session_id="sess1",
            workflow_name="wf",
            step="working",
            step_entered_at=datetime.now(UTC),
        )
        workflow_engine.state_manager.get_state.return_value = state

        working_step = WorkflowStep(name="working", allowed_tools="all", blocked_tools=[])
        wf = WorkflowDefinition(name="wf", steps=[working_step])
        workflow_engine.loader.load_workflow.return_value = wf

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"tool_name": "test_tool"},
            metadata={"_platform_session_id": "sess1"},
        )

        await workflow_engine.handle_event(event)

        mock_audit_manager.log_tool_call.assert_called()
