import pytest
from unittest.mock import MagicMock
from datetime import datetime, UTC
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.definitions import WorkflowState


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

    def test_check_exit_conditions_user_approval(self, evaluator, mock_state):
        # Current implementation just passes/TODO
        conditions = [{"type": "user_approval"}]
        # Should return True as it passes through the 'pass' block?
        # Re-reading code: if type == 'user_approval', it executes pass (lines 75-79),
        # then loops to next or finishes loop and returns True.
        assert evaluator.check_exit_conditions(conditions, mock_state) is True
