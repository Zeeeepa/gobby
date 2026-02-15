"""Tests for exit_conditions migration to simplified format.

Verifies that example workflow YAML files parse correctly and their
exit_conditions evaluate as expected — both before and after migration
to the simplified exit_when / string shorthand / approval sugar format.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.evaluator import ConditionEvaluator

pytestmark = pytest.mark.unit

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "docs" / "examples" / "workflows"


def _make_state(**variables: Any) -> WorkflowState:
    return WorkflowState(
        session_id="test-session",
        workflow_name="test-wf",
        step="test-step",
        variables=dict(variables),
    )


def _load_yaml(filename: str) -> dict[str, Any]:
    path = EXAMPLES_DIR / filename
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_steps(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get steps or phases from workflow data."""
    return data.get("steps", data.get("phases", []))


def _find_step_conditions(data: dict[str, Any], step_name: str) -> tuple[list, str | None]:
    """Find exit_conditions and exit_when for a named step."""
    for step in _get_steps(data):
        if step.get("name") == step_name:
            return step.get("exit_conditions", []), step.get("exit_when")
    raise ValueError(f"Step '{step_name}' not found")


def _get_approval_id(condition: dict[str, Any]) -> str:
    """Compute the approval condition ID the same way the evaluator does.

    When no explicit 'id' is provided, the evaluator normalizes the condition
    and uses SHA-256 of the JSON-serialized normalized dict.
    """
    if "id" in condition:
        return condition["id"]
    import hashlib
    import json

    normalized = ConditionEvaluator._normalize_condition(condition)
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()[:12]
    return f"approval_{digest}"


class TestAgentTddExitConditions:
    """Verify agent-tdd.yaml exit conditions evaluate correctly."""

    def test_understand_step_variable_set(self) -> None:
        """understand step exits when requirements_understood is set."""
        evaluator = ConditionEvaluator()
        data = _load_yaml("agent-tdd.yaml")
        conditions, exit_when = _find_step_conditions(data, "understand")

        state_unset = _make_state()
        state_set = _make_state(requirements_understood=True)

        assert (
            evaluator.check_exit_conditions(conditions, state_unset, exit_when=exit_when) is False
        )
        assert evaluator.check_exit_conditions(conditions, state_set, exit_when=exit_when) is True

    def test_write_tests_step_variable_set(self) -> None:
        """write_tests step exits when tests_written is set."""
        evaluator = ConditionEvaluator()
        data = _load_yaml("agent-tdd.yaml")
        conditions, exit_when = _find_step_conditions(data, "write_tests")

        state = _make_state(tests_written=True)
        assert evaluator.check_exit_conditions(conditions, state, exit_when=exit_when) is True

    def test_implement_step_variable_set(self) -> None:
        """implement step exits when tests_passing is set."""
        evaluator = ConditionEvaluator()
        data = _load_yaml("agent-tdd.yaml")
        conditions, exit_when = _find_step_conditions(data, "implement")

        state = _make_state(tests_passing=True)
        assert evaluator.check_exit_conditions(conditions, state, exit_when=exit_when) is True

    def test_refactor_step_user_approval(self) -> None:
        """refactor step exits when user approval is granted."""
        evaluator = ConditionEvaluator()
        data = _load_yaml("agent-tdd.yaml")
        conditions, exit_when = _find_step_conditions(data, "refactor")

        approval_cond = next(
            c
            for c in conditions
            if isinstance(c, dict) and (c.get("type") == "user_approval" or "approval" in c)
        )
        approval_id = _get_approval_id(approval_cond)

        state_not_approved = _make_state()
        state_approved = _make_state(**{f"_approval_{approval_id}_granted": True})

        assert (
            evaluator.check_exit_conditions(conditions, state_not_approved, exit_when=exit_when)
            is False
        )
        assert (
            evaluator.check_exit_conditions(conditions, state_approved, exit_when=exit_when) is True
        )


class TestPlanExecuteExitConditions:
    """Verify plan-execute.yaml exit conditions evaluate correctly."""

    def test_plan_step_user_approval(self) -> None:
        """plan step exits when user approval is granted."""
        evaluator = ConditionEvaluator()
        data = _load_yaml("plan-execute.yaml")
        conditions, exit_when = _find_step_conditions(data, "plan")

        approval_cond = next(
            c
            for c in conditions
            if isinstance(c, dict) and (c.get("type") == "user_approval" or "approval" in c)
        )
        approval_id = _get_approval_id(approval_cond)

        state_approved = _make_state(**{f"_approval_{approval_id}_granted": True})
        assert (
            evaluator.check_exit_conditions(conditions, state_approved, exit_when=exit_when) is True
        )


class TestArchitectExitConditions:
    """Verify architect.yaml exit conditions evaluate correctly."""

    def test_design_step_variable_set(self) -> None:
        """design step exits when design_doc is set."""
        evaluator = ConditionEvaluator()
        data = _load_yaml("architect.yaml")
        conditions, exit_when = _find_step_conditions(data, "design")

        state = _make_state(design_doc="arch-v1.md")
        assert evaluator.check_exit_conditions(conditions, state, exit_when=exit_when) is True

        state_unset = _make_state()
        assert (
            evaluator.check_exit_conditions(conditions, state_unset, exit_when=exit_when) is False
        )


class TestPlanToTasksExitConditions:
    """Verify plan-to-tasks.yaml exit conditions evaluate correctly."""

    def test_decompose_step_both_conditions(self) -> None:
        """decompose step needs both task_list set AND user approval."""
        evaluator = ConditionEvaluator()
        data = _load_yaml("plan-to-tasks.yaml")
        conditions, exit_when = _find_step_conditions(data, "decompose")

        approval_cond = next(
            c
            for c in conditions
            if isinstance(c, dict) and (c.get("type") == "user_approval" or "approval" in c)
        )
        approval_id = _get_approval_id(approval_cond)

        # Both conditions must be met (AND)
        state_both = _make_state(
            task_list=[{"id": 1, "title": "task"}],
            **{f"_approval_{approval_id}_granted": True},
        )
        assert evaluator.check_exit_conditions(conditions, state_both, exit_when=exit_when) is True

        # Only variable set, no approval
        state_var_only = _make_state(task_list=[{"id": 1}])
        assert (
            evaluator.check_exit_conditions(conditions, state_var_only, exit_when=exit_when)
            is False
        )
