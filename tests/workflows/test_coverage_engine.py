from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import (
    WorkflowDefinition,
    WorkflowRule,
    WorkflowState,
    WorkflowTransition,
)
from gobby.workflows.engine import WorkflowEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_components():
    loader = MagicMock()
    loader.load_workflow = AsyncMock()
    loader.discover_lifecycle_workflows = AsyncMock()
    state_manager = MagicMock()
    action_executor = AsyncMock()
    evaluator = MagicMock()
    audit_manager = MagicMock()

    # Nested mocks
    action_executor.db = MagicMock()
    action_executor.session_manager = MagicMock()
    action_executor.template_engine = MagicMock()
    action_executor.llm_service = MagicMock()
    action_executor.transcript_processor = MagicMock()
    action_executor.config = MagicMock()
    action_executor.mcp_manager = MagicMock()
    action_executor.memory_manager = MagicMock()
    action_executor.memory_sync_manager = MagicMock()
    action_executor.session_task_manager = MagicMock()
    action_executor.task_sync_manager = MagicMock()
    action_executor.pipeline_executor = MagicMock()
    action_executor.task_manager = MagicMock()

    return loader, state_manager, action_executor, evaluator, audit_manager


@pytest.fixture
def engine(mock_components):
    return WorkflowEngine(*mock_components)


def create_event(
    event_type: HookEventType = HookEventType.BEFORE_AGENT,
    session_id: str = "s1",
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> HookEvent:
    if data is None:
        data = {}
    if metadata is None:
        metadata = {"_platform_session_id": session_id}
    return HookEvent(
        event_type=event_type,
        session_id=session_id,
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data,
        metadata=metadata,
    )


@pytest.mark.asyncio
async def test_handle_event_no_session_id(engine):
    event = create_event(metadata={})
    assert (await engine.handle_event(event)).decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_no_state(engine, mock_components):
    _, state_manager, _, _, _ = mock_components
    state_manager.get_state.return_value = None
    event = create_event()
    assert (await engine.handle_event(event)).decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_disabled_workflow(engine, mock_components):
    _, state_manager, _, _, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="w1",
        step="working",
        step_entered_at=datetime.now(UTC),
        disabled=True,
        disabled_reason="maintenance",
    )
    state_manager.get_state.return_value = state

    event = create_event()
    assert (await engine.handle_event(event)).decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_stuck_workflow(engine, mock_components):
    loader, state_manager, _, _, _ = mock_components

    state = WorkflowState(
        session_id="s1",
        workflow_name="test_wf",
        step="thinking",
        step_entered_at=datetime.now(UTC) - timedelta(minutes=40),
        disabled=False,
    )
    state_manager.get_state.return_value = state

    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.name = "test_wf"
    reflect_step = MagicMock()
    reflect_step.on_enter = []
    reflect_step.on_exit = []
    wf.get_step.return_value = reflect_step
    loader.load_workflow.return_value = wf

    event = create_event()
    resp = await engine.handle_event(event)
    assert resp.decision == "modify"
    assert "Transitioning" in resp.context


@pytest.mark.asyncio
async def test_handle_event_workflow_not_found(engine, mock_components):
    loader, state_manager, _, _, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="missing",
        step="working",
        step_entered_at=datetime.now(UTC),
        disabled=False,
    )
    state_manager.get_state.return_value = state
    loader.load_workflow.return_value = None

    event = create_event()
    assert (await engine.handle_event(event)).decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_step_not_found(engine, mock_components):
    loader, state_manager, _, _, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="exists",
        step="unknown",
        step_entered_at=datetime.now(UTC),
        disabled=False,
    )
    state_manager.get_state.return_value = state

    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.name = "exists"
    wf.get_step.return_value = None
    loader.load_workflow.return_value = wf

    event = create_event()
    assert (await engine.handle_event(event)).decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_tool_blocking(engine, mock_components):
    loader, state_manager, _, evaluator, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="working",
        step_entered_at=datetime.now(UTC),
        disabled=False,
        approval_pending=False,
    )
    state_manager.get_state.return_value = state

    step = MagicMock()
    step.blocked_tools = []
    step.allowed_tools = "all"
    step.rules = []
    step.transitions = []
    step.exit_conditions = []

    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.get_step.return_value = step
    loader.load_workflow.return_value = wf

    event = create_event(event_type=HookEventType.BEFORE_TOOL)
    event.data["tool_name"] = "read_file"

    # 1. Approval Pending
    state.approval_pending = True
    assert (await engine.handle_event(event)).decision == "block"
    state.approval_pending = False

    # 2. Blocked List
    step.blocked_tools = ["read_file"]
    assert (await engine.handle_event(event)).decision == "block"
    step.blocked_tools = []

    # 3. Allowed List
    step.allowed_tools = ["other"]
    assert (await engine.handle_event(event)).decision == "block"
    step.allowed_tools = "all"

    # 4. Rules
    rule = WorkflowRule(when="True", action="block", name="block_read")
    step.rules = [rule]
    evaluator.evaluate.return_value = True
    assert (await engine.handle_event(event)).decision == "block"

    # 5. Fallthrough
    step.rules = []
    resp = await engine.handle_event(event)
    # BEFORE_TOOL allows by default if not blocked
    assert resp.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_exit_conditions(engine, mock_components):
    loader, state_manager, _, evaluator, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="final",
        step_entered_at=datetime.now(UTC),
        disabled=False,
    )
    state_manager.get_state.return_value = state
    step = MagicMock()
    step.exit_conditions = ["cond_done"]
    step.transitions = []
    step.rules = []

    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.get_step.return_value = step
    loader.load_workflow.return_value = wf

    # Use AFTER_TOOL to skip approval checks
    event = create_event(event_type=HookEventType.AFTER_TOOL)

    evaluator.check_exit_conditions.return_value = True

    assert (await engine.handle_event(event)).decision == "allow"
    assert evaluator.check_exit_conditions.called


@pytest.mark.asyncio
async def test_evaluate_lifecycle_full(engine, mock_components):
    loader, _, action_executor, evaluator, _ = mock_components

    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "lifecycle"
    wf.steps = []
    wf.variables = {}
    wf.name = "lifecycle_wf"
    wf.sources = None  # No source filter — applies to all sessions
    trigger1 = {"action": "act1", "when": "cond1"}
    wf.triggers = {"on_session_start": [trigger1]}
    wf.observers = []

    discovered = MagicMock()
    discovered.definition = wf
    discovered.name = "lifecycle_wf"
    loader.discover_lifecycle_workflows.return_value = [discovered]

    event = create_event(event_type=HookEventType.SESSION_START, data={"cwd": "/tmp"})
    loader.load_workflow.return_value = wf

    evaluator.evaluate.return_value = True
    action_executor.execute.return_value = {"inject_context": "ctx"}

    await engine.evaluate_all_lifecycle_workflows(event)
    assert action_executor.execute.call_count == 1


@pytest.mark.asyncio
async def test_evaluate_lifecycle_alias(engine, mock_components):
    loader, _, action_executor, evaluator, _ = mock_components
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "lifecycle"
    wf.steps = []
    wf.variables = {}
    wf.name = "alias_wf"
    wf.sources = None
    wf.triggers = {"on_prompt_submit": [{"action": "act1"}]}
    wf.observers = []

    discovered = MagicMock()
    discovered.definition = wf
    discovered.name = "alias_wf"
    loader.discover_lifecycle_workflows.return_value = [discovered]
    loader.load_workflow.return_value = wf

    event = create_event(event_type=HookEventType.BEFORE_AGENT)

    await engine.evaluate_all_lifecycle_workflows(event)
    assert action_executor.execute.call_count == 1


@pytest.mark.asyncio
async def test_transition_execution(engine, mock_components):
    loader, state_manager, action_executor, evaluator, _ = mock_components

    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="step1",
        step_entered_at=datetime.now(UTC),
        disabled=False,
    )
    state_manager.get_state.return_value = state

    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]

    step1 = MagicMock()
    step1.on_exit = [{"action": "log_exit"}]
    step1.transitions = [WorkflowTransition(when="True", to="step2")]

    step2 = MagicMock()
    step2.on_enter = [{"action": "log_enter"}]
    step2.transitions = []

    def get_step(name):
        if name == "step1":
            return step1
        if name == "step2":
            return step2
        return None

    wf.get_step.side_effect = get_step
    loader.load_workflow.return_value = wf

    event = create_event(event_type=HookEventType.AFTER_TOOL)
    evaluator.evaluate.return_value = True

    resp = await engine.handle_event(event)

    assert resp.decision == "modify"
    assert "Transitioning to step: step2" in resp.context

    calls = action_executor.execute.mock_calls
    assert len(calls) >= 2


@pytest.mark.asyncio
async def test_approval_flow_rejected(engine, mock_components):
    loader, state_manager, _, evaluator, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="step1",
        step_entered_at=datetime.now(UTC),
        disabled=False,
        approval_pending=True,
    )
    state_manager.get_state.return_value = state

    step1 = MagicMock()
    step1.rules = [WorkflowRule(when="True", action="require_approval", name="check")]
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.get_step.return_value = step1
    loader.load_workflow.return_value = wf

    # Event with rejection
    event = create_event(event_type=HookEventType.BEFORE_AGENT, data={"prompt": "no"})

    resp = await engine.handle_event(event)

    assert resp.decision == "block"
    assert state.approval_pending is False


@pytest.mark.asyncio
async def test_approval_flow_approved(engine, mock_components):
    loader, state_manager, _, evaluator, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="step1",
        step_entered_at=datetime.now(UTC),
        disabled=False,
        approval_pending=True,
    )
    state_manager.get_state.return_value = state

    step1 = MagicMock()
    step1.rules = []
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.get_step.return_value = step1
    loader.load_workflow.return_value = wf

    # Event with approval
    event = create_event(event_type=HookEventType.BEFORE_AGENT, data={"prompt": "yes"})

    resp = await engine.handle_event(event)

    assert resp.decision == "allow"
    assert state.approval_pending is False


@pytest.mark.asyncio
async def test_action_execution_exception(engine, mock_components):
    # Verify exception in _execute_actions is propagated
    _, state_manager, action_executor, _, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="working",
    )

    actions = [{"action": "boom"}]
    action_executor.execute.side_effect = Exception("Crash")

    with pytest.raises(Exception, match="Crash"):
        await engine._execute_actions(actions, state)


@pytest.mark.asyncio
async def test_lifecycle_workflow_not_found(engine, mock_components):
    loader, _, _, _, _ = mock_components
    loader.load_workflow.return_value = None

    # Check trigger evaluation directly
    event = create_event()
    resp = await engine.evaluate_lifecycle_triggers("missing_wf", event)
    assert resp.decision == "allow"


@pytest.mark.asyncio
async def test_lifecycle_trigger_alias_loop(engine, mock_components):
    loader, _, action_executor, _, _ = mock_components
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "lifecycle"
    wf.steps = []
    wf.triggers = {"on_alias_event": [{"action": "act1"}]}
    loader.load_workflow.return_value = wf

    event = create_event(event_type=HookEventType.BEFORE_AGENT)
    # Expected alias: on_prompt_submit

    wf.triggers = {"on_prompt_submit": [{"action": "act1"}]}

    await engine.evaluate_lifecycle_triggers("wf", event)

    assert action_executor.execute.called


@pytest.mark.asyncio
async def test_lifecycle_when_condition_false(engine, mock_components):
    loader, _, action_executor, evaluator, _ = mock_components
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "lifecycle"
    wf.steps = []
    wf.triggers = {"on_before_agent": [{"action": "act1", "when": "False"}]}
    loader.load_workflow.return_value = wf

    evaluator.evaluate.return_value = False

    event = create_event(event_type=HookEventType.BEFORE_AGENT)
    await engine.evaluate_lifecycle_triggers("wf", event)

    assert not action_executor.execute.called


@pytest.mark.asyncio
async def test_lifecycle_action_exception(engine, mock_components):
    loader, _, action_executor, _, _ = mock_components
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "lifecycle"
    wf.steps = []
    wf.triggers = {"on_before_agent": [{"action": "boom"}]}
    loader.load_workflow.return_value = wf

    action_executor.execute.side_effect = Exception("Crash")

    event = create_event(event_type=HookEventType.BEFORE_AGENT)
    # Should catch exception and log it, returning allow
    resp = await engine.evaluate_lifecycle_triggers("wf", event)

    assert resp.decision == "allow"


def test_audit_logging_exceptions(engine, mock_components):
    _, _, _, _, audit_manager = mock_components
    audit_manager.log_tool_call.side_effect = Exception("DB error")
    audit_manager.log_rule_eval.side_effect = Exception("DB error")
    audit_manager.log_transition.side_effect = Exception("DB error")

    # Verify no raise
    engine._log_tool_call("s1", "step", "tool", "allow")
    engine._log_rule_eval("s1", "step", "rule", "cond", "result")
    engine._log_transition("s1", "step1", "step2")


@pytest.mark.asyncio
async def test_lifecycle_context_none(engine, mock_components):
    # Call _evaluate_lifecycle_triggers directly with context_data=None
    loader, _, action_executor, _, _ = mock_components
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "lifecycle"
    wf.steps = []
    wf.triggers = {"on_before_agent": [{"action": "act1"}]}
    loader.load_workflow.return_value = wf

    action_executor.execute.return_value = {"key": "val"}

    event = create_event(event_type=HookEventType.BEFORE_AGENT)
    await engine.evaluate_lifecycle_triggers("wf", event, context_data=None)

    # Should handle None context gracefully
    assert action_executor.execute.called


@pytest.mark.asyncio
async def test_approval_request_trigger(engine, mock_components):
    loader, state_manager, _, evaluator, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="step1",
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        files_modified_this_task=0,
        approval_pending=False,
        disabled=False,
    )
    state_manager.get_state.return_value = state

    step1 = MagicMock()
    step1.exit_conditions = ["check"]
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.get_step.return_value = step1
    loader.load_workflow.return_value = wf

    # Eval logic returns needs_approval
    approval_res = MagicMock()
    approval_res.needs_approval = True
    approval_res.is_timed_out = False
    approval_res.condition_id = "cond1"
    approval_res.prompt = "Approve?"
    approval_res.timeout_seconds = 60
    evaluator.check_pending_approval.return_value = approval_res

    event = create_event(event_type=HookEventType.BEFORE_AGENT)
    resp = await engine.handle_event(event)

    assert resp.decision == "allow"
    assert "Approval Required" in resp.context
    assert state.approval_pending is True


@pytest.mark.asyncio
async def test_approval_timeout(engine, mock_components):
    loader, state_manager, _, evaluator, _ = mock_components
    state = WorkflowState(
        session_id="s1",
        workflow_name="wf",
        step="step1",
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        files_modified_this_task=0,
        approval_pending=False,
        disabled=False,
    )
    state_manager.get_state.return_value = state

    step1 = MagicMock()
    step1.exit_conditions = ["check"]
    wf = MagicMock(spec=WorkflowDefinition)
    wf.type = "step"
    wf.steps = [MagicMock()]
    wf.get_step.return_value = step1
    loader.load_workflow.return_value = wf

    # Eval logic returns timed_out
    approval_res = MagicMock()
    approval_res.needs_approval = False  # Logic checks this first
    approval_res.is_timed_out = True
    approval_res.condition_id = "cond1"
    approval_res.timeout_seconds = 60
    evaluator.check_pending_approval.return_value = approval_res

    event = create_event(event_type=HookEventType.BEFORE_AGENT)
    resp = await engine.handle_event(event)

    assert resp.decision == "block"
    assert "timed out" in resp.reason
