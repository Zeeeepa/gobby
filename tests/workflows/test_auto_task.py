"""
Tests for auto-task step workflow and related functionality.

Tests:
1. task_tree_complete() helper function
2. on_premature_stop handler
"""

from unittest.mock import MagicMock

import pytest

from gobby.workflows.definitions import (
    PrematureStopHandler,
    WorkflowDefinition,
)
from gobby.workflows.evaluator import ConditionEvaluator, task_tree_complete

pytestmark = pytest.mark.unit

# =============================================================================
# Test task_tree_complete() Helper Function
# =============================================================================


class TestTaskTreeComplete:
    """Tests for the task_tree_complete condition helper."""

    @pytest.fixture
    def mock_task_manager(self):
        """Create a mock task manager for testing."""
        return MagicMock()

    def test_returns_true_for_none_task_id(self, mock_task_manager) -> None:
        """Returns True when task_id is None (no task to check)."""
        assert task_tree_complete(mock_task_manager, None) is True

    def test_returns_true_for_empty_task_id(self, mock_task_manager) -> None:
        """Returns True when task_id is empty string."""
        assert task_tree_complete(mock_task_manager, "") is True

    def test_returns_false_when_no_task_manager(self) -> None:
        """Returns False when task_manager is None."""
        assert task_tree_complete(None, "gt-abc123") is False

    def test_returns_false_when_task_not_found(self, mock_task_manager) -> None:
        """Returns False when task is not found."""
        mock_task_manager.get_task.return_value = None
        assert task_tree_complete(mock_task_manager, "gt-missing") is False

    def test_returns_false_when_leaf_task_not_closed(self, mock_task_manager) -> None:
        """Returns False when a leaf task (no subtasks) is not closed."""
        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []  # Leaf task

        assert task_tree_complete(mock_task_manager, "gt-abc123") is False

    def test_returns_true_when_parent_in_progress_but_all_subtasks_closed(
        self, mock_task_manager
    ) -> None:
        """Returns True when parent is in_progress but all subtasks are closed.

        This is the core regression test for #8800: the auto-task workflow's
        task_tree_complete() condition must fire when a parent/epic task has all
        subtasks closed, even if the parent itself isn't explicitly closed yet.
        """
        parent_task = MagicMock()
        parent_task.status = "in_progress"

        subtask1 = MagicMock()
        subtask1.id = "gt-sub1"
        subtask1.status = "closed"

        subtask2 = MagicMock()
        subtask2.id = "gt-sub2"
        subtask2.status = "closed"

        def get_task_side_effect(task_id):
            tasks = {"gt-parent": parent_task, "gt-sub1": subtask1, "gt-sub2": subtask2}
            return tasks.get(task_id)

        def list_tasks_side_effect(parent_task_id=None):
            if parent_task_id == "gt-parent":
                return [subtask1, subtask2]
            return []

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect

        assert task_tree_complete(mock_task_manager, "gt-parent") is True

    def test_returns_false_when_parent_in_progress_with_incomplete_subtask(
        self, mock_task_manager
    ) -> None:
        """Returns False when parent is in_progress and some subtasks are still open."""
        parent_task = MagicMock()
        parent_task.status = "in_progress"

        subtask1 = MagicMock()
        subtask1.id = "gt-sub1"
        subtask1.status = "closed"

        subtask2 = MagicMock()
        subtask2.id = "gt-sub2"
        subtask2.status = "open"

        def get_task_side_effect(task_id):
            tasks = {"gt-parent": parent_task, "gt-sub1": subtask1, "gt-sub2": subtask2}
            return tasks.get(task_id)

        def list_tasks_side_effect(parent_task_id=None):
            if parent_task_id == "gt-parent":
                return [subtask1, subtask2]
            return []

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect

        assert task_tree_complete(mock_task_manager, "gt-parent") is False

    def test_returns_true_when_task_closed_no_subtasks(self, mock_task_manager) -> None:
        """Returns True when task is closed and has no subtasks."""
        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []  # No subtasks

        assert task_tree_complete(mock_task_manager, "gt-abc123") is True

    def test_returns_false_when_subtask_not_closed(self, mock_task_manager) -> None:
        """Returns False when any subtask is not closed."""
        parent_task = MagicMock()
        parent_task.status = "closed"

        # One closed, one open subtask
        subtask1 = MagicMock()
        subtask1.id = "gt-sub1"
        subtask1.status = "closed"

        subtask2 = MagicMock()
        subtask2.id = "gt-sub2"
        subtask2.status = "open"

        def get_task_side_effect(task_id):
            tasks = {"gt-abc123": parent_task, "gt-sub1": subtask1, "gt-sub2": subtask2}
            return tasks.get(task_id)

        mock_task_manager.get_task.side_effect = get_task_side_effect

        # Return subtasks only for parent, empty for subtasks (to prevent recursion)
        def list_tasks_side_effect(parent_task_id=None):
            if parent_task_id == "gt-abc123":
                return [subtask1, subtask2]
            return []

        mock_task_manager.list_tasks.side_effect = list_tasks_side_effect

        assert task_tree_complete(mock_task_manager, "gt-abc123") is False

    def test_returns_true_when_all_subtasks_closed(self, mock_task_manager) -> None:
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

    def test_handles_list_of_task_ids(self, mock_task_manager) -> None:
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

    def test_list_returns_false_if_any_incomplete(self, mock_task_manager) -> None:
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

    def test_evaluator_without_task_manager_returns_true(self) -> None:
        """task_tree_complete returns True when no task_manager registered."""
        evaluator = ConditionEvaluator()
        # No task_manager registered

        context = {"variables": {"session_task": "gt-abc123"}}
        result = evaluator.evaluate("task_tree_complete(variables.get('session_task'))", context)

        assert result is True  # No-op when no task_manager

    def test_evaluator_with_task_manager_evaluates_condition(self) -> None:
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

    def test_default_values(self) -> None:
        """Default action is guide_continuation with default message."""
        handler = PrematureStopHandler()
        assert handler.action == "guide_continuation"
        assert "suggest_next_task()" in handler.message
        assert handler.condition is None

    def test_custom_values(self) -> None:
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

    def test_definition_without_premature_stop(self) -> None:
        """WorkflowDefinition defaults to None for on_premature_stop."""
        definition = WorkflowDefinition(name="test", steps=[])
        assert definition.on_premature_stop is None
        assert definition.exit_condition is None

    def test_definition_with_premature_stop(self) -> None:
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
