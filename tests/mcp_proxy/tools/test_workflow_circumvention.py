"""Tests for workflow circumvention prevention.

These tests verify that agents cannot bypass workflow controls:
1. Manual transitions to steps with conditional auto-transitions are blocked
2. Modifying session_task when a real workflow is active is blocked
"""

from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.workflows import create_workflows_registry
from gobby.workflows.definitions import WorkflowState

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock()


@pytest.fixture
def mock_state_manager():
    """Create a mock workflow state manager."""
    return MagicMock()


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    manager = MagicMock()
    # Make resolve_session_reference return the input unchanged (for testing)
    manager.resolve_session_reference.side_effect = lambda ref, project_id=None: ref
    return manager


@pytest.fixture
def mock_loader():
    """Create a mock workflow loader."""
    loader = MagicMock()
    loader.global_dirs = []
    return loader


@pytest.fixture
def registry(mock_loader, mock_state_manager, mock_session_manager, mock_db):
    """Create workflow registry for testing."""
    return create_workflows_registry(
        loader=mock_loader,
        state_manager=mock_state_manager,
        session_manager=mock_session_manager,
        db=mock_db,
    )


def call_tool(registry, tool_name: str, **kwargs):
    """Helper to call a tool from the registry synchronously."""
    tool = registry._tools.get(tool_name)
    if not tool:
        raise ValueError(f"Tool '{tool_name}' not found")
    return tool.func(**kwargs)


class TestBlockManualTransitionToConditionalSteps:
    """Tests for blocking manual transitions to steps with conditional auto-transitions."""

    def test_blocks_manual_transition_to_conditional_step(
        self, registry, mock_loader, mock_state_manager
    ) -> None:
        """Manual transition to step with conditional auto-transition is blocked."""
        # Setup mock state in "work" step
        mock_state = MagicMock()
        mock_state.workflow_name = "auto-task"
        mock_state.step = "work"
        mock_state_manager.get_state.return_value = mock_state

        # Setup mock workflow with work -> complete conditional transition
        mock_work_step = MagicMock()
        mock_work_step.name = "work"
        mock_transition = MagicMock()
        mock_transition.to = "complete"
        mock_transition.when = "task_tree_complete(variables.session_task)"
        mock_work_step.transitions = [mock_transition]

        mock_complete_step = MagicMock()
        mock_complete_step.name = "complete"
        mock_complete_step.transitions = []

        mock_workflow = MagicMock()
        mock_workflow.steps = [mock_work_step, mock_complete_step]
        mock_loader.load_workflow.return_value = mock_workflow

        # Try to manually transition to "complete"
        result = call_tool(
            registry,
            "request_step_transition",
            to_step="complete",
            session_id="test-session",
        )

        assert "error" in result
        assert "conditional auto-transition" in result["error"]
        assert "task_tree_complete" in result["error"]
        assert "workflow circumvention" in result["error"]

    def test_allows_manual_transition_without_condition(
        self, registry, mock_loader, mock_state_manager
    ) -> None:
        """Manual transition to step without conditional auto-transition is allowed."""
        # Setup mock state
        mock_state = MagicMock()
        mock_state.workflow_name = "plan-execute"
        mock_state.step = "plan"
        mock_state_manager.get_state.return_value = mock_state

        # Setup mock workflow without conditional transitions
        mock_plan_step = MagicMock()
        mock_plan_step.name = "plan"
        mock_plan_step.transitions = []  # No transitions at all

        mock_execute_step = MagicMock()
        mock_execute_step.name = "execute"
        mock_execute_step.transitions = []

        mock_workflow = MagicMock()
        mock_workflow.steps = [mock_plan_step, mock_execute_step]
        mock_loader.load_workflow.return_value = mock_workflow

        # Manual transition should work
        result = call_tool(
            registry,
            "request_step_transition",
            to_step="execute",
            session_id="test-session",
        )

        assert "error" not in result
        assert result["to_step"] == "execute"

    def test_allows_transition_to_step_with_unconditional_transition(
        self, registry, mock_loader, mock_state_manager
    ) -> None:
        """Manual transition is allowed when transition has no 'when' condition."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.step = "step1"
        mock_state_manager.get_state.return_value = mock_state

        # Transition without 'when' condition
        mock_step1 = MagicMock()
        mock_step1.name = "step1"
        mock_transition = MagicMock()
        mock_transition.to = "step2"
        mock_transition.when = None  # No condition
        mock_step1.transitions = [mock_transition]

        mock_step2 = MagicMock()
        mock_step2.name = "step2"
        mock_step2.transitions = []

        mock_workflow = MagicMock()
        mock_workflow.steps = [mock_step1, mock_step2]
        mock_loader.load_workflow.return_value = mock_workflow

        result = call_tool(
            registry,
            "request_step_transition",
            to_step="step2",
            session_id="test-session",
        )

        assert "error" not in result

    def test_blocks_only_transitions_to_conditional_targets(
        self, registry, mock_loader, mock_state_manager
    ) -> None:
        """Transition to a different step (not the conditional target) is allowed."""
        mock_state = MagicMock()
        mock_state.workflow_name = "multi-step"
        mock_state.step = "step1"
        mock_state_manager.get_state.return_value = mock_state

        # step1 has conditional transition to step3, but we try to go to step2
        mock_step1 = MagicMock()
        mock_step1.name = "step1"
        mock_conditional = MagicMock()
        mock_conditional.to = "step3"  # Conditional goes to step3
        mock_conditional.when = "some_condition()"
        mock_step1.transitions = [mock_conditional]

        mock_step2 = MagicMock()
        mock_step2.name = "step2"
        mock_step2.transitions = []

        mock_step3 = MagicMock()
        mock_step3.name = "step3"
        mock_step3.transitions = []

        mock_workflow = MagicMock()
        mock_workflow.steps = [mock_step1, mock_step2, mock_step3]
        mock_loader.load_workflow.return_value = mock_workflow

        # Transition to step2 (not step3) should work
        result = call_tool(
            registry,
            "request_step_transition",
            to_step="step2",
            session_id="test-session",
        )

        assert "error" not in result
        assert result["to_step"] == "step2"


class TestBlockSessionTaskModification:
    """Tests for blocking session_task modification when workflow is active."""

    def test_blocks_session_task_modification_with_active_workflow(
        self, registry, mock_state_manager
    ) -> None:
        """Cannot modify session_task when a real workflow is active."""
        # Setup mock state with active workflow and existing session_task
        mock_state = MagicMock(spec=WorkflowState)
        mock_state.workflow_name = "auto-task"
        mock_state.variables = {"session_task": "gt-parent-123"}
        mock_state_manager.get_state.return_value = mock_state

        # Try to change session_task
        result = call_tool(
            registry,
            "set_variable",
            name="session_task",
            value="gt-child-456",
            session_id="test-session",
        )

        assert "error" in result
        assert "Cannot modify session_task" in result["error"]
        assert "auto-task" in result["error"]
        assert "gt-parent-123" in result["error"]

    def test_allows_session_task_modification_with_lifecycle_workflow(
        self, registry, mock_state_manager
    ) -> None:
        """Can modify session_task when only __lifecycle__ workflow is active."""
        mock_state = MagicMock(spec=WorkflowState)
        mock_state.workflow_name = "__lifecycle__"
        mock_state.variables = {"session_task": "gt-old-task"}
        mock_state_manager.get_state.return_value = mock_state

        result = call_tool(
            registry,
            "set_variable",
            name="session_task",
            value="gt-new-task",
            session_id="test-session",
        )

        assert "error" not in result
        # Should have deprecation warning
        assert "warning" in result
        assert "DEPRECATED" in result["warning"]

    def test_allows_session_task_modification_with_no_state(
        self, registry, mock_state_manager
    ) -> None:
        """Can set session_task when no workflow state exists."""
        mock_state_manager.get_state.return_value = None

        result = call_tool(
            registry,
            "set_variable",
            name="session_task",
            value="gt-new-task",
            session_id="test-session",
        )

        assert "error" not in result
        # Should still save state and show warning
        mock_state_manager.save_state.assert_called_once()

    def test_allows_initial_session_task_setting(self, registry, mock_state_manager) -> None:
        """Can set session_task for the first time even with active workflow."""
        # Workflow active but session_task not yet set
        mock_state = MagicMock(spec=WorkflowState)
        mock_state.workflow_name = "auto-task"
        mock_state.variables = {}  # No session_task yet
        mock_state_manager.get_state.return_value = mock_state

        result = call_tool(
            registry,
            "set_variable",
            name="session_task",
            value="gt-initial-task",
            session_id="test-session",
        )

        # Should allow since there's no existing value to protect
        assert "error" not in result

    def test_allows_setting_same_session_task_value(self, registry, mock_state_manager) -> None:
        """Setting session_task to same value is allowed (idempotent)."""
        mock_state = MagicMock(spec=WorkflowState)
        mock_state.workflow_name = "auto-task"
        mock_state.variables = {"session_task": "gt-same-task"}
        mock_state_manager.get_state.return_value = mock_state

        result = call_tool(
            registry,
            "set_variable",
            name="session_task",
            value="gt-same-task",  # Same value
            session_id="test-session",
        )

        assert "error" not in result

    def test_allows_other_variable_modification_with_active_workflow(
        self, registry, mock_state_manager
    ) -> None:
        """Other variables can still be modified when workflow is active."""
        mock_state = MagicMock(spec=WorkflowState)
        mock_state.workflow_name = "auto-task"
        mock_state.variables = {"session_task": "gt-task-123", "other_var": "old"}
        mock_state_manager.get_state.return_value = mock_state

        result = call_tool(
            registry,
            "set_variable",
            name="other_var",
            value="new",
            session_id="test-session",
        )

        assert result == {}

    def test_blocks_session_task_modification_suggests_end_workflow(
        self, registry, mock_state_manager
    ) -> None:
        """Error message suggests using end_workflow first."""
        mock_state = MagicMock(spec=WorkflowState)
        mock_state.workflow_name = "auto-task"
        mock_state.variables = {"session_task": "gt-current"}
        mock_state_manager.get_state.return_value = mock_state

        result = call_tool(
            registry,
            "set_variable",
            name="session_task",
            value="gt-different",
            session_id="test-session",
        )

        assert "error" in result
        assert "end_workflow()" in result["error"]
