from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import WorkflowDefinition, WorkflowStep
from gobby.workflows.engine import WorkflowEngine

pytestmark = pytest.mark.unit


def make_event(
    event_type: HookEventType = HookEventType.BEFORE_TOOL,
    session_id: str = "test-session",
    metadata: dict | None = None,
    data: dict | None = None,
    cwd: str | None = None,
) -> HookEvent:
    """Helper to create HookEvent with required fields."""
    return HookEvent(
        event_type=event_type,
        session_id=session_id,
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data or {},
        metadata=metadata or {},
        cwd=cwd,
    )


@pytest.fixture
def mock_loader():
    loader = Mock()
    loader.load_workflow = AsyncMock()
    loader.discover_lifecycle_workflows = AsyncMock()
    return loader


@pytest.fixture
def mock_state_manager():
    return Mock()


@pytest.fixture
def mock_action_executor():
    """Create a mock ActionExecutor for WorkflowEngine tests.

    Attributes exercised by tests in this file:
    - execute(): Called in test_evaluate_lifecycle_workflows_blocked

    Attributes NOT exercised (but set up for interface compatibility):
    - session_manager: WorkflowEngine accesses .find_by_external_id() in handle_event
      but tests exit early before reaching that code path
    - db, template_engine, llm_service, transcript_processor, config,
      tool_proxy_getter, memory_manager, memory_sync_manager, task_sync_manager,
      session_task_manager: Only passed through to ActionContext, not
      directly called in these tests
    """
    # Import here to avoid circular imports and for spec
    from gobby.workflows.actions import ActionExecutor

    # Use spec (not spec_set) since we need to set instance attributes that
    # are only defined in __init__. spec still catches typos in method names.
    executor = AsyncMock(spec=ActionExecutor)

    # Sub-mocks: these are accessed as attributes but not called in current tests.
    # Using plain Mock() since the tests don't exercise their methods.
    # TODO: Add spec_set when tests are expanded to exercise these collaborators.
    executor.session_manager = Mock()
    executor.db = Mock()
    executor.template_engine = Mock()
    executor.llm_service = Mock()
    executor.transcript_processor = Mock()
    executor.config = Mock()
    executor.tool_proxy_getter = Mock()
    executor.memory_manager = Mock()
    executor.memory_sync_manager = Mock()
    executor.task_sync_manager = Mock()
    executor.session_task_manager = Mock()
    executor.skill_manager = Mock()
    executor.pipeline_executor = Mock()
    executor.workflow_loader = Mock()
    return executor


@pytest.fixture
def engine(mock_loader, mock_state_manager, mock_action_executor):
    return WorkflowEngine(
        loader=mock_loader, state_manager=mock_state_manager, action_executor=mock_action_executor
    )


@pytest.mark.asyncio
async def test_handle_event_no_session_id(engine, mock_state_manager):
    event = make_event(metadata={})
    response = await engine.handle_event(event)
    assert response.decision == "allow"
    # Should not attempt to get state when no session_id is present
    mock_state_manager.get_state.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_no_state(engine, mock_state_manager):
    mock_state_manager.get_state.return_value = None
    event = make_event(metadata={"_platform_session_id": "sess-123"})
    response = await engine.handle_event(event)
    assert response.decision == "allow"
    # Should look up state for the session
    mock_state_manager.get_state.assert_called_once_with("sess-123")
    # Should not attempt to update state when none exists
    mock_state_manager.set_state.assert_not_called()
    mock_state_manager.update_state.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_disabled_workflow(engine, mock_state_manager):
    state = MagicMock()
    state.disabled = True
    state.disabled_reason = "testing"
    state.workflow_name = "test-wf"
    state.step_entered_at = None
    mock_state_manager.get_state.return_value = state

    event = make_event(metadata={"_platform_session_id": "sess-123"})
    response = await engine.handle_event(event)
    assert response.decision == "allow"
    # Should look up state for the session
    mock_state_manager.get_state.assert_called_once_with("sess-123")
    # Should not transition or update state for disabled workflows
    mock_state_manager.set_state.assert_not_called()
    mock_state_manager.update_state.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_lifecycle_state(engine, mock_state_manager):
    state = MagicMock()
    state.disabled = False
    state.workflow_name = "__lifecycle__"
    state.step_entered_at = None
    mock_state_manager.get_state.return_value = state

    event = make_event(metadata={"_platform_session_id": "sess-123"})
    response = await engine.handle_event(event)
    assert response.decision == "allow"
    # Should look up state for the session
    mock_state_manager.get_state.assert_called_once_with("sess-123")
    # Should not transition or update state for lifecycle workflows
    mock_state_manager.set_state.assert_not_called()
    mock_state_manager.update_state.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_workflow_not_found(engine, mock_state_manager, mock_loader):
    state = MagicMock()
    state.disabled = False
    state.workflow_name = "unknown-wf"
    state.variables = {}
    state.step_entered_at = None
    mock_state_manager.get_state.return_value = state
    mock_loader.load_workflow.return_value = None

    event = make_event(cwd="/tmp", metadata={"_platform_session_id": "sess-123"})
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_lifecycle_workflow_type(engine, mock_state_manager, mock_loader):
    state = MagicMock()
    state.disabled = False
    state.workflow_name = "lifecycle-wf"
    state.variables = {}
    state.step_entered_at = None
    mock_state_manager.get_state.return_value = state

    workflow = Mock(spec=WorkflowDefinition)
    workflow.type = "lifecycle"
    workflow.name = "lifecycle-wf"
    mock_loader.load_workflow.return_value = workflow

    event = make_event(cwd="/tmp", metadata={"_platform_session_id": "sess-123"})
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_step_not_found(engine, mock_state_manager, mock_loader):
    state = MagicMock()
    state.disabled = False
    state.workflow_name = "test-wf"
    state.step = "unknown-step"
    state.variables = {}
    state.step_entered_at = None
    mock_state_manager.get_state.return_value = state

    workflow = Mock(spec=WorkflowDefinition)
    workflow.type = "step"
    workflow.name = "test-wf"
    workflow.get_step.return_value = None
    mock_loader.load_workflow.return_value = workflow

    event = make_event(
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
        data={"tool_name": "test_tool"},
    )
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_handle_approval(engine, mock_state_manager, mock_loader):
    state = MagicMock()
    state.disabled = False
    state.workflow_name = "test-wf"
    state.step = "current-step"
    state.approval_pending = False
    state.variables = {}
    state.step_entered_at = None
    state.session_id = "sess-123"
    mock_state_manager.get_state.return_value = state

    workflow = Mock(spec=WorkflowDefinition)
    workflow.type = "step"
    step = Mock(spec=WorkflowStep)
    step.blocked_tools = []
    step.allowed_tools = "all"
    step.rules = []
    step.transitions = []
    step.exit_conditions = []
    workflow.get_step.return_value = step
    mock_loader.load_workflow.return_value = workflow

    # Mock evaluator to require approval
    engine.evaluator.check_pending_approval = Mock()
    approval_check = Mock()
    approval_check.needs_approval = True
    approval_check.condition_id = "cond1"
    approval_check.prompt = "Approve?"
    approval_check.timeout_seconds = 60
    engine.evaluator.check_pending_approval.return_value = approval_check

    event = make_event(
        event_type=HookEventType.BEFORE_AGENT,
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
        data={"prompt": "hello"},
    )

    response = await engine.handle_event(event)
    assert response.decision == "allow"  # Should allow prompt but notification context
    assert "Approval Required" in response.context
    assert state.approval_pending is True


@pytest.mark.asyncio
async def test_evaluate_lifecycle_workflows_none(engine, mock_loader):
    mock_loader.discover_lifecycle_workflows.return_value = []

    event = make_event(cwd="/tmp", metadata={"_platform_session_id": "sess-123"})

    response = await engine.evaluate_all_lifecycle_workflows(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_evaluate_lifecycle_workflows_blocked(
    engine, mock_loader, mock_state_manager, mock_action_executor
):
    # Configure state_manager to return None so we don't hit Mock attribute issues
    mock_state_manager.get_state.return_value = None

    workflow = Mock(spec=WorkflowDefinition)
    workflow.name = "block-wf"
    workflow.triggers = {"on_before_tool": [{"action": "block_action"}]}
    workflow.variables = {}

    discovered = Mock()
    discovered.definition = workflow
    discovered.name = "block-wf"

    mock_loader.discover_lifecycle_workflows.return_value = [discovered]

    # Mock action execution to block
    mock_action_executor.execute.return_value = {"decision": "block", "reason": "blocked by policy"}

    event = make_event(
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
        data={"source": "test"},
    )

    response = await engine.evaluate_all_lifecycle_workflows(event)
    assert response.decision == "block"
    assert response.reason == "blocked by policy"


@pytest.mark.asyncio
async def test_execute_actions_passes_skill_manager(engine, mock_action_executor):
    """Verify _execute_actions wires skill_manager from ActionExecutor to ActionContext."""
    from gobby.workflows.actions import ActionContext

    state = MagicMock()
    state.session_id = "sess-abc"
    actions = [{"action": "inject_context", "source": "skills"}]

    mock_action_executor.execute.return_value = None

    await engine._execute_actions(actions, state)

    # The ActionContext passed to execute should have skill_manager set
    call_args = mock_action_executor.execute.call_args
    context_arg = call_args[0][1]  # second positional arg is context
    assert isinstance(context_arg, ActionContext)
    assert context_arg.skill_manager is mock_action_executor.skill_manager
