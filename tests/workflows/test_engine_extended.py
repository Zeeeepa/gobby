from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.storage.workflow_audit import WorkflowAuditManager
from gobby.workflows.actions import ActionExecutor
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_loader():
    return MagicMock(spec=WorkflowLoader)


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
    executor.mcp_manager = MagicMock()
    executor.memory_manager = MagicMock()
    executor.memory_sync_manager = MagicMock()
    executor.session_task_manager = MagicMock()
    executor.task_sync_manager = MagicMock()
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

        # Need phase for get_step() call in handle_event
        wf = MagicMock()
        wf.get_step.return_value = MagicMock(name="working_step")
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

        wf = MagicMock()
        wf.get_step.return_value = MagicMock(name="working_step")
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

        wf = MagicMock()
        step = MagicMock(name="working_step")
        wf.get_step.return_value = step
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

    async def test_lifecycle_loop_and_aliases(
        self, workflow_engine, mock_loader, mock_action_executor, mock_evaluator, mock_state_manager
    ):
        # Test:
        # 1. Alias lookup (on_before_agent -> on_prompt_submit)
        # 2. Loop mechanism (action triggers change in state -> triggers next cycle?)
        # Actually loop depends on separate triggers firing.

        # No step workflow state for this lifecycle-only test
        mock_state_manager.get_state.return_value = None

        wf = MagicMock(spec=WorkflowDefinition)
        wf.name = "lifecycle_wf"
        wf.variables = {}  # Workflow-level variables
        # Triggers using ALIAS
        wf.triggers = {
            "on_prompt_submit": [  # Alias for on_before_agent
                {"action": "act_alias", "when": "cond_true"},
                {"action": "act_false", "when": "cond_false"},
            ],
            "on_tool_call": [],  # Empty
        }

        container = MagicMock()
        container.definition = wf

        mock_loader.discover_lifecycle_workflows.return_value = [container]

        # Mock evaluator
        def eval_side_effect(condition, context):
            return condition == "cond_true"

        mock_evaluator.evaluate.side_effect = eval_side_effect

        event = HookEvent(
            event_type=HookEventType.BEFORE_AGENT,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )

        # Action execution
        mock_action_executor.execute.return_value = {"executed": True}

        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)

        assert response.decision == "allow"
        # Should have executed act_alias but NOT act_false
        args_list = mock_action_executor.execute.call_args_list
        assert len(args_list) == 1
        assert args_list[0][0][0] == "act_alias"

    async def test_audit_logging_failure(self, workflow_engine, mock_audit_manager):
        # Force exception in audit logging
        mock_audit_manager.log_tool_call.side_effect = Exception("Audit Error")

        # Should not raise exception
        workflow_engine._log_tool_call("sess", "step", "tool", "allow")

    async def test_lifecycle_blocking(self, workflow_engine, mock_loader):
        """Test that actions returning decision='block' propagate through lifecycle workflows."""
        wf = MagicMock(spec=WorkflowDefinition)
        wf.name = "blocker"
        wf.variables = {}
        wf.triggers = {"on_session_start": [{"action": "block_action"}]}

        container = MagicMock()
        container.definition = wf
        container.name = "blocker"

        mock_loader.discover_lifecycle_workflows.return_value = [container]

        # Action returns block decision
        workflow_engine.action_executor.execute.return_value = {
            "decision": "block",
            "reason": "Test block reason",
        }

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )

        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)

        assert response.decision == "block"
        assert response.reason == "Test block reason"

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

        wf = MagicMock()
        step = MagicMock()
        step.exit_conditions = ["cond"]
        wf.get_step.return_value = step
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

    async def test_no_lifecycle_workflows(self, workflow_engine, mock_loader):
        mock_loader.discover_lifecycle_workflows.return_value = []
        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )
        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)
        assert response.decision == "allow"

    async def test_trigger_execution_result_processing(
        self, workflow_engine, mock_loader, mock_action_executor
    ):
        # Test 1: System message update
        # Test 2: Inject context
        # Test 3: Multiple triggers

        wf = MagicMock(spec=WorkflowDefinition)
        wf.name = "sys_msg_wf"
        wf.variables = {}
        wf.triggers = {"on_session_start": [{"action": "act1"}]}

        container = MagicMock()
        container.definition = wf
        mock_loader.discover_lifecycle_workflows.return_value = [container]

        # Action returns system_message
        mock_action_executor.execute.return_value = {
            "system_message": "New System Prompt",
            "inject_context": "Added Context",
        }

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )

        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)

        assert response.system_message == "New System Prompt"
        assert "Added Context" in response.context

    async def test_lifecycle_decision_propagation(
        self, workflow_engine, mock_loader, mock_action_executor
    ):
        """Test that non-blocking actions result in 'allow' decision."""
        wf = MagicMock(spec=WorkflowDefinition)
        wf.name = "allow_wf"
        wf.variables = {}
        wf.triggers = {"on_session_start": [{"action": "normal_action"}]}

        container = MagicMock()
        container.definition = wf
        container.name = "allow_wf"

        mock_loader.discover_lifecycle_workflows.return_value = [container]

        # Action returns data but no block decision
        workflow_engine.action_executor.execute.return_value = {
            "some_key": "some_value",
            "inject_context": "Injected context",
        }

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )

        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)

        assert response.decision == "allow"
        assert "Injected context" in response.context

    async def test_lifecycle_when_condition_skip(
        self, workflow_engine, mock_loader, mock_evaluator
    ):
        wf = MagicMock(spec=WorkflowDefinition)
        wf.name = "conditional"
        wf.variables = {}
        # Condition that evals to False
        wf.triggers = {"on_session_start": [{"action": "act", "when": "skip_me"}]}

        container = MagicMock()
        container.definition = wf
        mock_loader.discover_lifecycle_workflows.return_value = [container]

        mock_evaluator.evaluate.return_value = False

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )

        await workflow_engine.evaluate_all_lifecycle_workflows(event)

        # Action executor should NOT be called
        workflow_engine.action_executor.execute.assert_not_called()

    async def test_lifecycle_action_exception(
        self, workflow_engine, mock_loader, mock_action_executor
    ):
        # Force exception in action execution
        wf = MagicMock(spec=WorkflowDefinition)
        wf.name = "error_wf"
        wf.variables = {}
        wf.triggers = {"on_session_start": [{"action": "act1"}]}

        container = MagicMock()
        container.definition = wf
        mock_loader.discover_lifecycle_workflows.return_value = [container]

        mock_action_executor.execute.side_effect = Exception("Action Failed")

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )

        # Should NOT raise, just log error
        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)
        assert response.decision == "allow"

    async def test_context_accumulation(self, workflow_engine, mock_loader, mock_action_executor):
        # Ensure context data flows between workflows if engine handles it (it doesn't currently chaining across wfs?)
        # evaluate_all_lifecycle_workflows iterates workflows.
        # It aggregates context string lists.
        # It does NOT pass context_data from one WF to another?
        # Let's check engine.py
        # Result of one WF is just HookResponse.
        # Context data is internal to `_evaluate_workflow_triggers`?
        # Yes, lines 523: `variables=context_data or {},`.
        # And `_evaluate_workflow_triggers` takes `context_data`.
        # BUT `evaluate_all_lifecycle_workflows` calls:
        # `response = await self._evaluate_workflow_triggers(container.definition, event, context_data)`
        # AND `context_data` is initialized to {} in line 402?
        # Wait, I need to see line 402.
        # But if I test multiple triggers IN THE SAME WORKFLOW, they share `context_data`?
        # `_evaluate_workflow_triggers` iterates triggers.
        # Yes, line 617: `for trigger in triggers:`
        # And it passes `context_data` to action context? No, it uses `state.variables`.
        # And it updates `context_data` in line 713.
        # So YES, multiple triggers in ONE workflow share context.

        wf = MagicMock(spec=WorkflowDefinition)
        wf.name = "chain_wf"
        wf.variables = {}
        # Two triggers for SAME event?
        # The map is `trigger_name` -> list of triggers.
        # So yes, a list of triggers.
        wf.triggers = {"on_session_start": [{"action": "act1"}, {"action": "act2"}]}

        container = MagicMock()
        container.definition = wf
        mock_loader.discover_lifecycle_workflows.return_value = [container]

        # Mock execute to return data
        mock_action_executor.execute.side_effect = [{"key1": "val1"}, {"key2": "val2"}]

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={},
        )

        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)

        # Verify both actions were executed
        assert mock_action_executor.execute.call_count == 2

        # Verify the action calls were made with correct action types
        call_args_list = mock_action_executor.execute.call_args_list
        assert call_args_list[0][0][0] == "act1"  # First action type
        assert call_args_list[1][0][0] == "act2"  # Second action type

        # Verify the response indicates success (allow decision)
        assert response.decision == "allow"

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

    async def test_evaluate_lifecycle_workflows(
        self, workflow_engine, mock_loader, mock_action_executor
    ):
        # Setup mocking for 2 lifecycle workflows
        wf1 = MagicMock(spec=WorkflowDefinition)
        wf1.name = "wf1"
        wf1.variables = {}
        # Triggers:
        # wf1: on_before_tool -> action1
        wf1.triggers = {"on_before_tool": [{"action": "act1", "param": "p1"}]}

        wf2 = MagicMock(spec=WorkflowDefinition)
        wf2.name = "wf2"
        wf2.variables = {}
        # wf2: on_before_tool -> action2
        wf2.triggers = {"on_before_tool": [{"action": "act2", "param": "p2"}]}

        # discover_lifecycle_workflows returns a container with .definition
        container1 = MagicMock()
        container1.definition = wf1
        container1.name = "wf1"

        container2 = MagicMock()
        container2.definition = wf2
        container2.name = "wf2"

        mock_loader.discover_lifecycle_workflows.return_value = [container1, container2]

        # Mock action execution
        mock_action_executor.execute.side_effect = [
            {"inject_context": "CTX1"},  # act1
            {"inject_context": "CTX2"},  # act2
        ]

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"cwd": "/tmp"},
            metadata={"_platform_session_id": "sess1"},
        )

        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)

        assert response.decision == "allow"
        assert "CTX1" in response.context
        assert "CTX2" in response.context
        assert mock_action_executor.execute.call_count == 2

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

        wf = MagicMock()
        step = MagicMock(name="working")
        step.blocked_tools = []
        step.allowed_tools = "all"
        wf.get_step.return_value = step
        workflow_engine.loader.load_workflow.return_value = wf

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="sess1",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={},
            metadata={"_platform_session_id": "sess1"},
        )
        event.data["tool_name"] = "test_tool"

        await workflow_engine.handle_event(event)

        mock_audit_manager.log_tool_call.assert_called()
