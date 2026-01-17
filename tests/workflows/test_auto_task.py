"""
Tests for auto-task step workflow and related functionality.

Tests:
1. task_tree_complete() helper function
2. on_premature_stop handler
3. activate_workflow with variables for auto-task
4. Workflow loading and structure
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gobby.workflows.definitions import (
    PrematureStopHandler,
    WorkflowDefinition,
    WorkflowState,
)
from gobby.workflows.evaluator import ConditionEvaluator, task_tree_complete
from gobby.workflows.loader import WorkflowLoader

# =============================================================================
# Test task_tree_complete() Helper Function
# =============================================================================


class TestTaskTreeComplete:
    """Tests for the task_tree_complete condition helper."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager for testing."""
        return MagicMock()

    def test_returns_true_for_none_task_id(self, mock_task_manager):
        """Returns True when task_id is None (no task to check)."""
        assert task_tree_complete(mock_task_manager, None) is True

    def test_returns_true_for_empty_task_id(self, mock_task_manager):
        """Returns True when task_id is empty string."""
        assert task_tree_complete(mock_task_manager, "") is True

    def test_returns_false_when_no_task_manager(self):
        """Returns False when task_manager is None."""
        assert task_tree_complete(None, "gt-abc123") is False

    def test_returns_false_when_task_not_found(self, mock_task_manager):
        """Returns False when task is not found."""
        mock_task_manager.get_task.return_value = None
        assert task_tree_complete(mock_task_manager, "gt-missing") is False

    def test_returns_false_when_task_not_closed(self, mock_task_manager):
        """Returns False when main task is not closed."""
        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        assert task_tree_complete(mock_task_manager, "gt-abc123") is False

    def test_returns_true_when_task_closed_no_subtasks(self, mock_task_manager):
        """Returns True when task is closed and has no subtasks."""
        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []  # No subtasks

        assert task_tree_complete(mock_task_manager, "gt-abc123") is True

    def test_returns_false_when_subtask_not_closed(self, mock_task_manager):
        """Returns False when any subtask is not closed."""
        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task

        # One closed, one open subtask
        subtask1 = MagicMock()
        subtask1.id = "gt-sub1"
        subtask1.status = "closed"

        subtask2 = MagicMock()
        subtask2.id = "gt-sub2"
        subtask2.status = "open"

        # Return subtasks only for parent, empty for subtasks (to prevent recursion)
        def list_tasks_side_effect(parent_task_id=None):
            if parent_task_id == "gt-abc123":
                return [subtask1, subtask2]
            return []

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect

        assert task_tree_complete(mock_task_manager, "gt-abc123") is False

    def test_returns_true_when_all_subtasks_closed(self, mock_task_manager):
        """Returns True when all subtasks are closed."""
        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task

        subtask1 = MagicMock()
        subtask1.id = "gt-sub1"
        subtask1.status = "closed"

        subtask2 = MagicMock()
        subtask2.id = "gt-sub2"
        subtask2.status = "closed"

        # Return subtasks only for parent, empty for subtasks
        def list_tasks_side_effect(parent_task_id=None):
            if parent_task_id == "gt-abc123":
                return [subtask1, subtask2]
            return []

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect

        assert task_tree_complete(mock_task_manager, "gt-abc123") is True

    def test_handles_list_of_task_ids(self, mock_task_manager):
        """Handles list of task IDs - all must be complete."""
        task1 = MagicMock()
        task1.status = "closed"
        task2 = MagicMock()
        task2.status = "closed"

        def get_task_side_effect(task_id):
            tasks = {"gt-1": task1, "gt-2": task2}
            return tasks.get(task_id)

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []

        assert task_tree_complete(mock_task_manager, ["gt-1", "gt-2"]) is True

    def test_list_returns_false_if_any_incomplete(self, mock_task_manager):
        """Returns False if any task in list is incomplete."""
        task1 = MagicMock()
        task1.status = "closed"
        task2 = MagicMock()
        task2.status = "open"  # Not closed

        def get_task_side_effect(task_id):
            tasks = {"gt-1": task1, "gt-2": task2}
            return tasks.get(task_id)

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = []

        assert task_tree_complete(mock_task_manager, ["gt-1", "gt-2"]) is False


# =============================================================================
# Test ConditionEvaluator with task_tree_complete
# =============================================================================


class TestConditionEvaluatorTaskHelpers:
    """Tests for task helpers in ConditionEvaluator."""

    def test_evaluator_without_task_manager_returns_true(self):
        """task_tree_complete returns True when no task_manager registered."""
        evaluator = ConditionEvaluator()
        # No task_manager registered

        context = {"variables": {"session_task": "gt-abc123"}}
        result = evaluator.evaluate("task_tree_complete(variables.get('session_task'))", context)

        assert result is True  # No-op when no task_manager

    def test_evaluator_with_task_manager_evaluates_condition(self):
        """task_tree_complete uses registered task_manager."""
        evaluator = ConditionEvaluator()

        # Mock task manager
        mock_tm = MagicMock()
        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_tm.get_task.return_value = mock_task
        mock_tm.list_tasks.return_value = []

        evaluator.register_task_manager(mock_tm)

        context = {"variables": {"session_task": "gt-abc123"}}
        result = evaluator.evaluate("task_tree_complete(variables.get('session_task'))", context)

        assert result is True
        mock_tm.get_task.assert_called_with("gt-abc123")


# =============================================================================
# Test PrematureStopHandler Model
# =============================================================================


class TestPrematureStopHandler:
    """Tests for PrematureStopHandler model."""

    def test_default_values(self):
        """Default action is guide_continuation with default message."""
        handler = PrematureStopHandler()
        assert handler.action == "guide_continuation"
        assert "suggest_next_task()" in handler.message
        assert handler.condition is None

    def test_custom_values(self):
        """Custom values are accepted."""
        handler = PrematureStopHandler(
            action="block",
            message="Custom message",
            condition="some_condition()",
        )
        assert handler.action == "block"
        assert handler.message == "Custom message"
        assert handler.condition == "some_condition()"


# =============================================================================
# Test WorkflowDefinition with on_premature_stop
# =============================================================================


class TestWorkflowDefinitionPrematureStop:
    """Tests for on_premature_stop in WorkflowDefinition."""

    def test_definition_without_premature_stop(self):
        """WorkflowDefinition defaults to None for on_premature_stop."""
        definition = WorkflowDefinition(name="test", steps=[])
        assert definition.on_premature_stop is None
        assert definition.exit_condition is None

    def test_definition_with_premature_stop(self):
        """WorkflowDefinition accepts on_premature_stop."""
        definition = WorkflowDefinition(
            name="test",
            steps=[],
            exit_condition="current_step == 'complete'",
            on_premature_stop=PrematureStopHandler(
                action="guide_continuation",
                message="Keep working!",
            ),
        )
        assert definition.exit_condition == "current_step == 'complete'"
        assert definition.on_premature_stop is not None
        assert definition.on_premature_stop.action == "guide_continuation"


# =============================================================================
# Test auto-task Workflow Loading
# =============================================================================


@pytest.mark.integration
class TestAutonomousTaskWorkflowLoading:
    """Tests for loading the auto-task workflow."""

    def test_workflow_can_be_loaded(self):
        """auto-task.yaml workflow can be loaded."""
        # Use the actual shared workflows directory
        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        workflow = loader.load_workflow("auto-task")

        assert workflow is not None
        assert workflow.name == "auto-task"
        assert workflow.type == "step"

    def test_workflow_has_expected_steps(self):
        """auto-task workflow has work and complete steps."""
        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        workflow = loader.load_workflow("auto-task")

        assert workflow is not None
        step_names = [s.name for s in workflow.steps]
        assert "work" in step_names
        assert "complete" in step_names

    def test_workflow_has_exit_condition(self):
        """auto-task workflow has exit_condition defined."""
        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        workflow = loader.load_workflow("auto-task")

        assert workflow is not None
        assert workflow.exit_condition is not None
        assert "complete" in workflow.exit_condition

    def test_workflow_has_premature_stop_handler(self):
        """auto-task workflow has on_premature_stop defined."""
        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        workflow = loader.load_workflow("auto-task")

        assert workflow is not None
        assert workflow.on_premature_stop is not None
        assert workflow.on_premature_stop.action == "guide_continuation"

    def test_work_step_has_transition_to_complete(self):
        """Work step has transition to complete with task_tree_complete condition."""
        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        workflow = loader.load_workflow("auto-task")

        work_step = workflow.get_step("work")
        assert work_step is not None
        assert len(work_step.transitions) > 0

        # Find the transition to 'complete' (may not be the first one if research step exists)
        complete_transition = None
        for transition in work_step.transitions:
            if transition.to == "complete":
                complete_transition = transition
                break

        assert complete_transition is not None, "No transition to 'complete' step found"
        assert "task_tree_complete" in complete_transition.when


# =============================================================================
# Test activate_workflow with variables for auto-task
# =============================================================================


@pytest.mark.integration
class TestActivateWorkflowWithVariables:
    """Tests for activate_workflow MCP tool with variables parameter."""

    @pytest.fixture
    def state_manager(self, temp_db):
        """Create WorkflowStateManager with test database."""
        from gobby.workflows.state_manager import WorkflowStateManager

        return WorkflowStateManager(temp_db)

    @pytest.fixture
    def session_id(self, temp_db):
        """Create a session and return its ID."""
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        project_manager = LocalProjectManager(temp_db)
        project = project_manager.get_or_create("/tmp/test-project")

        session_manager = LocalSessionManager(temp_db)
        session = session_manager.register(
            external_id="ext_auto_001",
            machine_id="machine_001",
            source="claude_code",
            project_id=project.id,
        )
        return session.id

    def test_requires_session_id(self, temp_db):
        """Tool requires session_id parameter."""
        from gobby.mcp_proxy.tools.workflows import create_workflows_registry
        from gobby.workflows.loader import WorkflowLoader
        from gobby.workflows.state_manager import WorkflowStateManager

        # Need loader with workflow directory
        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        state_manager = WorkflowStateManager(temp_db)

        registry = create_workflows_registry(loader=loader, state_manager=state_manager)
        tool_func = registry._tools["activate_workflow"].func

        result = tool_func(name="auto-task", variables={"session_task": "gt-abc123"})

        assert result["success"] is False
        assert "session_id is required" in result["error"]

    def test_creates_workflow_state_with_variables(self, temp_db, session_id):
        """Tool creates workflow state with variables merged correctly."""
        from gobby.mcp_proxy.tools.workflows import create_workflows_registry
        from gobby.workflows.loader import WorkflowLoader
        from gobby.workflows.state_manager import WorkflowStateManager

        # Set up with actual workflow directory
        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        state_manager = WorkflowStateManager(temp_db)

        registry = create_workflows_registry(loader=loader, state_manager=state_manager)
        tool_func = registry._tools["activate_workflow"].func

        result = tool_func(
            name="auto-task",
            variables={"session_task": "gt-abc123"},
            session_id=session_id,
        )

        assert result["success"] is True
        assert result["workflow"] == "auto-task"
        # Note: shared/workflows/auto-task.yaml uses "research" as first step
        assert result["step"] == "research"
        assert result["variables"]["session_task"] == "gt-abc123"

        # Verify state was saved
        state = state_manager.get_state(session_id)
        assert state is not None
        assert state.workflow_name == "auto-task"
        assert state.variables.get("session_task") == "gt-abc123"

    def test_merges_workflow_defaults_with_passed_variables(self, temp_db, session_id):
        """Passed variables override workflow defaults."""
        from gobby.mcp_proxy.tools.workflows import create_workflows_registry
        from gobby.workflows.loader import WorkflowLoader
        from gobby.workflows.state_manager import WorkflowStateManager

        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        state_manager = WorkflowStateManager(temp_db)

        registry = create_workflows_registry(loader=loader, state_manager=state_manager)
        tool_func = registry._tools["activate_workflow"].func

        # Override the default premature_stop_max_attempts
        result = tool_func(
            name="auto-task",
            variables={"session_task": "gt-abc123", "premature_stop_max_attempts": 5},
            session_id=session_id,
        )

        assert result["success"] is True
        # Verify override worked
        assert result["variables"]["premature_stop_max_attempts"] == 5
        assert result["variables"]["session_task"] == "gt-abc123"

    def test_rejects_existing_step_workflow(self, temp_db, session_id):
        """Tool rejects activation if step workflow already active."""
        from gobby.mcp_proxy.tools.workflows import create_workflows_registry
        from gobby.workflows.loader import WorkflowLoader
        from gobby.workflows.state_manager import WorkflowStateManager

        workflow_dir = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        state_manager = WorkflowStateManager(temp_db)

        # Create existing workflow state
        existing_state = WorkflowState(
            session_id=session_id,
            workflow_name="plan-execute",
            step="plan",
        )
        state_manager.save_state(existing_state)

        registry = create_workflows_registry(loader=loader, state_manager=state_manager)
        tool_func = registry._tools["activate_workflow"].func

        result = tool_func(
            name="auto-task",
            variables={"session_task": "gt-abc123"},
            session_id=session_id,
        )

        assert result["success"] is False
        assert "already has step workflow" in result["error"]
