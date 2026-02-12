from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.evaluator import (
    APPROVAL_KEYWORDS,
    REJECTION_KEYWORDS,
    ConditionEvaluator,
    check_approval_response,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def evaluator():
    return ConditionEvaluator()


@pytest.fixture
def mock_state():
    state = MagicMock(spec=WorkflowState)
    state.step_action_count = 5
    state.total_action_count = 10
    state.variables = {"foo": "bar", "count": 10}
    state.task_list = []
    # Ensure attributes accessed by evaluator exist on instance (MagicMock handles this via spec, but flattened context accesses them)
    # The evaluator flattens state into context:
    # "step_action_count": state.step_action_count,
    # "total_action_count": state.total_action_count,
    # "variables": state.variables,
    # "task_list": state.task_list,
    return state


class TestConditionEvaluator:
    def test_evaluate_simple_expression(self, evaluator) -> None:
        context = {"a": 1, "b": 2}
        assert evaluator.evaluate("a < b", context) is True
        assert evaluator.evaluate("a > b", context) is False

    def test_evaluate_with_helpers(self, evaluator) -> None:
        context = {"items": [1, 2, 3]}
        assert evaluator.evaluate("len(items) == 3", context) is True

    def test_evaluate_invalid_expression(self, evaluator) -> None:
        context = {}
        # Should return False on error and log warning
        assert evaluator.evaluate("invalid_syntax(}}", context) is False
        assert evaluator.evaluate("unknown_var > 0", context) is False

    def test_check_exit_conditions_variable_set_met(self, evaluator, mock_state) -> None:
        conditions = [{"type": "variable_set", "variable": "foo"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is True

    def test_check_exit_conditions_variable_set_not_met(self, evaluator, mock_state) -> None:
        conditions = [{"type": "variable_set", "variable": "missing_var"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_check_exit_conditions_expression_met(self, evaluator, mock_state) -> None:
        conditions = [{"type": "expression", "expression": "step_action_count == 5"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is True

    def test_check_exit_conditions_expression_not_met(self, evaluator, mock_state) -> None:
        conditions = [{"type": "expression", "expression": "total_action_count > 100"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_check_exit_conditions_multiple(self, evaluator, mock_state) -> None:
        conditions = [
            {"type": "variable_set", "variable": "foo"},
            {"type": "expression", "expression": "count == 10"},
        ]
        assert evaluator.check_exit_conditions(conditions, mock_state) is True

    def test_check_exit_conditions_multiple_fail(self, evaluator, mock_state) -> None:
        conditions = [
            {"type": "variable_set", "variable": "foo"},
            {"type": "expression", "expression": "count == 999"},  # False
        ]
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_boolean_and_expression(self, evaluator) -> None:
        """Boolean 'and' with variable access — used in workflow when clauses."""
        context = {"task_claimed": True, "plan_mode": False}
        assert evaluator.evaluate("task_claimed and not plan_mode", context) is True
        assert evaluator.evaluate("task_claimed and plan_mode", context) is False

    def test_boolean_or_expression(self, evaluator) -> None:
        context = {"a": False, "b": True}
        assert evaluator.evaluate("a or b", context) is True
        assert evaluator.evaluate("a or False", context) is False

    def test_comparison_expression(self, evaluator) -> None:
        context = {"step_action_count": 5}
        assert evaluator.evaluate("step_action_count > 3", context) is True
        assert evaluator.evaluate("step_action_count == 5", context) is True
        assert evaluator.evaluate("step_action_count > 10", context) is False

    def test_yaml_boolean_aliases(self, evaluator) -> None:
        """YAML uses lowercase true/false — evaluator must handle them."""
        context = {"x": True}
        assert evaluator.evaluate("x == true", context) is True
        assert evaluator.evaluate("x == false", context) is False

    def test_dict_get_method_call(self, evaluator) -> None:
        """Test .get() on dict — used in variables.get('key', default)."""
        context = {"variables": {"task_claimed": True}}
        assert evaluator.evaluate("variables.get('task_claimed', False)", context) is True
        assert evaluator.evaluate("variables.get('missing_key', False)", context) is False

    def test_mcp_called_helper(self, evaluator) -> None:
        """Test mcp_called() function — used in workflow gates."""
        context = {
            "variables": {"mcp_calls": {"gobby-tasks": ["create_task", "close_task"]}}
        }
        assert evaluator.evaluate("mcp_called('gobby-tasks', 'close_task')", context) is True
        assert evaluator.evaluate("mcp_called('gobby-tasks', 'unknown')", context) is False

    def test_mcp_result_is_null_helper(self, evaluator) -> None:
        context = {
            "variables": {"mcp_results": {"gobby-tasks": {"suggest": None}}}
        }
        assert evaluator.evaluate("mcp_result_is_null('gobby-tasks', 'suggest')", context) is True

    def test_mcp_failed_helper(self, evaluator) -> None:
        context = {
            "variables": {
                "mcp_results": {"gobby-tasks": {"close_task": {"success": False, "error": "err"}}}
            }
        }
        assert evaluator.evaluate("mcp_failed('gobby-tasks', 'close_task')", context) is True

    def test_mcp_result_has_helper(self, evaluator) -> None:
        context = {
            "variables": {
                "mcp_results": {"gobby-tasks": {"wait": {"timed_out": True}}}
            }
        }
        assert evaluator.evaluate("mcp_result_has('gobby-tasks', 'wait', 'timed_out', True)", context) is True

    def test_task_tree_complete_with_manager(self) -> None:
        """Test task_tree_complete() with registered task manager."""
        ev = ConditionEvaluator()
        tm = MagicMock()
        task = MagicMock()
        task.status = "closed"
        tm.get_task.return_value = task
        tm.list_tasks.return_value = []
        ev.register_task_manager(tm)

        context = {}
        assert ev.evaluate("task_tree_complete('task-123')", context) is True

    def test_has_stop_signal_with_registry(self) -> None:
        """Test has_stop_signal() with registered stop registry."""
        ev = ConditionEvaluator()
        sr = MagicMock()
        sr.has_pending_signal.return_value = True
        ev.register_stop_registry(sr)

        context = {}
        assert ev.evaluate("has_stop_signal('session-abc')", context) is True

    def test_empty_condition_returns_true(self, evaluator) -> None:
        assert evaluator.evaluate("", {}) is True

    def test_none_constant(self, evaluator) -> None:
        context = {"x": None}
        assert evaluator.evaluate("x == None", context) is True

    def test_check_exit_conditions_user_approval_not_granted(self, evaluator, mock_state) -> None:
        """User approval condition returns False when not yet granted."""
        conditions = [{"type": "user_approval", "id": "test_approval"}]
        mock_state.variables = {}
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_check_exit_conditions_user_approval_granted(self, evaluator, mock_state) -> None:
        """User approval condition returns True when granted."""
        conditions = [{"type": "user_approval", "id": "test_approval"}]
        mock_state.variables = {"_approval_test_approval_granted": True}
        assert evaluator.check_exit_conditions(conditions, mock_state) is True


class TestApprovalResponse:
    """Tests for check_approval_response function."""

    def test_approval_keywords(self) -> None:
        """Test that all approval keywords are recognized."""
        for keyword in APPROVAL_KEYWORDS:
            assert check_approval_response(keyword) == "approved"
            assert check_approval_response(keyword.upper()) == "approved"
            assert check_approval_response(f"  {keyword}  ") == "approved"

    def test_rejection_keywords(self) -> None:
        """Test that all rejection keywords are recognized."""
        for keyword in REJECTION_KEYWORDS:
            assert check_approval_response(keyword) == "rejected"
            assert check_approval_response(keyword.upper()) == "rejected"
            assert check_approval_response(f"  {keyword}  ") == "rejected"

    def test_approval_with_continuation(self) -> None:
        """Test approval keyword at start of longer message."""
        assert check_approval_response("yes, let's proceed") == "approved"
        assert check_approval_response("ok sounds good") == "approved"
        assert check_approval_response("no, I don't want that") == "rejected"

    def test_no_keyword(self) -> None:
        """Test that non-keyword input returns None."""
        assert check_approval_response("what do you mean?") is None
        assert check_approval_response("maybe later") is None
        assert check_approval_response("I'm not sure") is None
        assert check_approval_response("") is None


class TestCheckPendingApproval:
    """Tests for check_pending_approval method."""

    @pytest.fixture
    def state(self):
        """Create a real WorkflowState for testing."""
        return WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )

    def test_no_approval_conditions(self, evaluator, state) -> None:
        """No approval conditions returns None."""
        conditions = [{"type": "expression", "expression": "true"}]
        result = evaluator.check_pending_approval(conditions, state)
        assert result is None

    def test_needs_approval(self, evaluator, state) -> None:
        """Returns needs_approval when approval not yet requested."""
        conditions = [{"type": "user_approval", "id": "test", "prompt": "Ready to proceed?"}]
        result = evaluator.check_pending_approval(conditions, state)
        assert result is not None
        assert result.needs_approval is True
        assert result.condition_id == "test"
        assert result.prompt == "Ready to proceed?"

    def test_already_approved(self, evaluator, state) -> None:
        """Returns None when already approved."""
        conditions = [{"type": "user_approval", "id": "test"}]
        state.variables["_approval_test_granted"] = True
        result = evaluator.check_pending_approval(conditions, state)
        assert result is None

    def test_already_rejected(self, evaluator, state) -> None:
        """Returns is_rejected when previously rejected."""
        conditions = [{"type": "user_approval", "id": "test"}]
        state.variables["_approval_test_rejected"] = True
        result = evaluator.check_pending_approval(conditions, state)
        assert result is not None
        assert result.is_rejected is True

    def test_timeout(self, evaluator, state) -> None:
        """Returns is_timed_out when timeout exceeded."""
        conditions = [{"type": "user_approval", "id": "test", "timeout": 60}]
        state.approval_pending = True
        state.approval_condition_id = "test"
        state.approval_requested_at = datetime.now(UTC) - timedelta(seconds=120)
        result = evaluator.check_pending_approval(conditions, state)
        assert result is not None
        assert result.is_timed_out is True

    def test_default_prompt(self, evaluator, state) -> None:
        """Uses default prompt when none specified."""
        conditions = [{"type": "user_approval", "id": "test"}]
        result = evaluator.check_pending_approval(conditions, state)
        assert result.prompt == "Do you approve this action? (yes/no)"
