import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.definitions import WorkflowState, WorkflowDefinition, WorkflowStep
from gobby.hooks.events import HookEvent, HookEventType, HookResponse


@pytest.fixture
def mock_loader():
    return Mock()


@pytest.fixture
def mock_state_manager():
    return Mock()


@pytest.fixture
def mock_action_executor():
    executor = AsyncMock()
    executor.session_manager = Mock()
    executor.db = Mock()
    executor.template_engine = Mock()
    executor.llm_service = Mock()
    executor.transcript_processor = Mock()
    executor.config = Mock()
    executor.mcp_manager = Mock()
    executor.memory_manager = Mock()
    executor.memory_sync_manager = Mock()
    executor.task_sync_manager = Mock()
    executor.session_task_manager = Mock()
    return executor


@pytest.fixture
def engine(mock_loader, mock_state_manager, mock_action_executor):
    return WorkflowEngine(
        loader=mock_loader, state_manager=mock_state_manager, action_executor=mock_action_executor
    )


@pytest.mark.asyncio
async def test_handle_event_no_session_id(engine):
    event = HookEvent(event_type=HookEventType.BEFORE_TOOL, metadata={})
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_no_state(engine, mock_state_manager):
    mock_state_manager.get_state.return_value = None
    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL, metadata={"_platform_session_id": "sess-123"}
    )
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_disabled_workflow(engine, mock_state_manager):
    state = Mock(spec=WorkflowState)
    state.disabled = True
    state.disabled_reason = "testing"
    state.workflow_name = "test-wf"
    mock_state_manager.get_state.return_value = state

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL, metadata={"_platform_session_id": "sess-123"}
    )
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_lifecycle_state(engine, mock_state_manager):
    state = Mock(spec=WorkflowState)
    state.disabled = False
    state.workflow_name = "__lifecycle__"
    mock_state_manager.get_state.return_value = state

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL, metadata={"_platform_session_id": "sess-123"}
    )
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_workflow_not_found(engine, mock_state_manager, mock_loader):
    state = Mock(spec=WorkflowState)
    state.disabled = False
    state.workflow_name = "unknown-wf"
    state.variables = {}
    mock_state_manager.get_state.return_value = state
    mock_loader.load_workflow.return_value = None

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
    )
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_lifecycle_workflow_type(engine, mock_state_manager, mock_loader):
    state = Mock(spec=WorkflowState)
    state.disabled = False
    state.workflow_name = "lifecycle-wf"
    state.variables = {}
    mock_state_manager.get_state.return_value = state

    workflow = Mock(spec=WorkflowDefinition)
    workflow.type = "lifecycle"
    workflow.name = "lifecycle-wf"
    mock_loader.load_workflow.return_value = workflow

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
    )
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_step_not_found(engine, mock_state_manager, mock_loader):
    state = Mock(spec=WorkflowState)
    state.disabled = False
    state.workflow_name = "test-wf"
    state.step = "unknown-step"
    state.variables = {}
    mock_state_manager.get_state.return_value = state

    workflow = Mock(spec=WorkflowDefinition)
    workflow.type = "step"
    workflow.name = "test-wf"
    workflow.get_step.return_value = None
    mock_loader.load_workflow.return_value = workflow

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
        data={"tool_name": "test_tool"},
    )
    response = await engine.handle_event(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_handle_event_handle_approval(engine, mock_state_manager, mock_loader):
    state = MagicMock(spec=WorkflowState)
    state.disabled = False
    state.workflow_name = "test-wf"
    state.step = "current-step"
    state.approval_pending = False
    state.variables = {}
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

    event = HookEvent(
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

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
    )

    response = await engine.evaluate_all_lifecycle_workflows(event)
    assert response.decision == "allow"


@pytest.mark.asyncio
async def test_evaluate_lifecycle_workflows_blocked(engine, mock_loader, mock_action_executor):
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

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        cwd="/tmp",
        metadata={"_platform_session_id": "sess-123"},
        data={"source": "test"},
    )

    response = await engine.evaluate_all_lifecycle_workflows(event)
    assert response.decision == "block"
    assert response.reason == "blocked by policy"
