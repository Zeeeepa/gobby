from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.evaluator import (
    APPROVAL_KEYWORDS,
    REJECTION_KEYWORDS,
    ApprovalCheckResult,
    ConditionEvaluator,
    check_approval_response,
)


@pytest.fixture
def evaluator():
    return ConditionEvaluator()


@pytest.fixture
def mock_state():
    state = MagicMock(spec=WorkflowState)
    state.phase_action_count = 5
    state.total_action_count = 10
    state.variables = {"foo": "bar", "count": 10}
    state.task_list = []
    # Ensure attributes accessed by evaluator exist on instance (MagicMock handles this via spec, but flattened context accesses them)
    # The evaluator flattens state into context:
    # "phase_action_count": state.phase_action_count,
    # "total_action_count": state.total_action_count,
    # "variables": state.variables,
    # "task_list": state.task_list,
    return state


class TestConditionEvaluator:
    def test_evaluate_simple_expression(self, evaluator):
        context = {"a": 1, "b": 2}
        assert evaluator.evaluate("a < b", context) is True
        assert evaluator.evaluate("a > b", context) is False

    def test_evaluate_with_helpers(self, evaluator):
        context = {"items": [1, 2, 3]}
        assert evaluator.evaluate("len(items) == 3", context) is True

    def test_evaluate_invalid_expression(self, evaluator):
        context = {}
        # Should return False on error and log warning
        assert evaluator.evaluate("invalid_syntax(}}", context) is False
        assert evaluator.evaluate("unknown_var > 0", context) is False

    def test_check_exit_conditions_variable_set_met(self, evaluator, mock_state):
        conditions = [{"type": "variable_set", "variable": "foo"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is True

    def test_check_exit_conditions_variable_set_not_met(self, evaluator, mock_state):
        conditions = [{"type": "variable_set", "variable": "missing_var"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_check_exit_conditions_expression_met(self, evaluator, mock_state):
        conditions = [{"type": "expression", "expression": "phase_action_count == 5"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is True

    def test_check_exit_conditions_expression_not_met(self, evaluator, mock_state):
        conditions = [{"type": "expression", "expression": "total_action_count > 100"}]
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_check_exit_conditions_multiple(self, evaluator, mock_state):
        conditions = [
            {"type": "variable_set", "variable": "foo"},
            {"type": "expression", "expression": "count == 10"},
        ]
        assert evaluator.check_exit_conditions(conditions, mock_state) is True

    def test_check_exit_conditions_multiple_fail(self, evaluator, mock_state):
        conditions = [
            {"type": "variable_set", "variable": "foo"},
            {"type": "expression", "expression": "count == 999"},  # False
        ]
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_check_exit_conditions_user_approval_not_granted(self, evaluator, mock_state):
        """User approval condition returns False when not yet granted."""
        conditions = [{"type": "user_approval", "id": "test_approval"}]
        mock_state.variables = {}
        assert evaluator.check_exit_conditions(conditions, mock_state) is False

    def test_check_exit_conditions_user_approval_granted(self, evaluator, mock_state):
        """User approval condition returns True when granted."""
        conditions = [{"type": "user_approval", "id": "test_approval"}]
        mock_state.variables = {"_approval_test_approval_granted": True}
        assert evaluator.check_exit_conditions(conditions, mock_state) is True


class TestApprovalResponse:
    """Tests for check_approval_response function."""

    def test_approval_keywords(self):
        """Test that all approval keywords are recognized."""
        for keyword in APPROVAL_KEYWORDS:
            assert check_approval_response(keyword) == "approved"
            assert check_approval_response(keyword.upper()) == "approved"
            assert check_approval_response(f"  {keyword}  ") == "approved"

    def test_rejection_keywords(self):
        """Test that all rejection keywords are recognized."""
        for keyword in REJECTION_KEYWORDS:
            assert check_approval_response(keyword) == "rejected"
            assert check_approval_response(keyword.upper()) == "rejected"
            assert check_approval_response(f"  {keyword}  ") == "rejected"

    def test_approval_with_continuation(self):
        """Test approval keyword at start of longer message."""
        assert check_approval_response("yes, let's proceed") == "approved"
        assert check_approval_response("ok sounds good") == "approved"
        assert check_approval_response("no, I don't want that") == "rejected"

    def test_no_keyword(self):
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
            phase="test-phase",
        )

    def test_no_approval_conditions(self, evaluator, state):
        """No approval conditions returns None."""
        conditions = [{"type": "expression", "expression": "true"}]
        result = evaluator.check_pending_approval(conditions, state)
        assert result is None

    def test_needs_approval(self, evaluator, state):
        """Returns needs_approval when approval not yet requested."""
        conditions = [
            {"type": "user_approval", "id": "test", "prompt": "Ready to proceed?"}
        ]
        result = evaluator.check_pending_approval(conditions, state)
        assert result is not None
        assert result.needs_approval is True
        assert result.condition_id == "test"
        assert result.prompt == "Ready to proceed?"

    def test_already_approved(self, evaluator, state):
        """Returns None when already approved."""
        conditions = [{"type": "user_approval", "id": "test"}]
        state.variables["_approval_test_granted"] = True
        result = evaluator.check_pending_approval(conditions, state)
        assert result is None

    def test_already_rejected(self, evaluator, state):
        """Returns is_rejected when previously rejected."""
        conditions = [{"type": "user_approval", "id": "test"}]
        state.variables["_approval_test_rejected"] = True
        result = evaluator.check_pending_approval(conditions, state)
        assert result is not None
        assert result.is_rejected is True

    def test_timeout(self, evaluator, state):
        """Returns is_timed_out when timeout exceeded."""
        conditions = [{"type": "user_approval", "id": "test", "timeout": 60}]
        state.approval_pending = True
        state.approval_condition_id = "test"
        state.approval_requested_at = datetime.now(UTC) - timedelta(seconds=120)
        result = evaluator.check_pending_approval(conditions, state)
        assert result is not None
        assert result.is_timed_out is True

    def test_default_prompt(self, evaluator, state):
        """Uses default prompt when none specified."""
        conditions = [{"type": "user_approval", "id": "test"}]
        result = evaluator.check_pending_approval(conditions, state)
        assert result.prompt == "Do you approve this action? (yes/no)"
