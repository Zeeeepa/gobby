"""Tests for observer declarations in session-lifecycle.yaml.

Verifies: session-lifecycle.yaml declares behavior observers for
task_claim_tracking, detect_plan_mode, and mcp_call_tracking.
These observers replace hardcoded detect_* calls in lifecycle_evaluator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gobby.workflows.definitions import WorkflowDefinition

pytestmark = pytest.mark.unit

LIFECYCLE_YAML = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "gobby"
    / "install"
    / "shared"
    / "workflows"
    / "session-lifecycle.yaml"
)


@pytest.fixture
def lifecycle_data() -> dict:
    """Load and return the raw YAML data from session-lifecycle.yaml."""
    with open(LIFECYCLE_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def lifecycle_workflow(lifecycle_data: dict) -> WorkflowDefinition:
    """Parse session-lifecycle.yaml into a WorkflowDefinition."""
    return WorkflowDefinition(**lifecycle_data)


class TestSessionLifecycleObservers:
    def test_yaml_loads_with_observers(self, lifecycle_data: dict) -> None:
        """session-lifecycle.yaml should parse and include an observers field."""
        assert "observers" in lifecycle_data, "session-lifecycle.yaml should have an 'observers' field"
        assert len(lifecycle_data["observers"]) == 3

    def test_workflow_definition_parses_observers(self, lifecycle_workflow: WorkflowDefinition) -> None:
        """WorkflowDefinition should parse observers from session-lifecycle.yaml."""
        assert len(lifecycle_workflow.observers) == 3

    def test_task_claim_tracking_observer_declared(self, lifecycle_workflow: WorkflowDefinition) -> None:
        """task_claim_tracking behavior should be declared as an observer."""
        behaviors = {obs.behavior for obs in lifecycle_workflow.observers if obs.behavior}
        assert "task_claim_tracking" in behaviors

    def test_detect_plan_mode_observer_declared(self, lifecycle_workflow: WorkflowDefinition) -> None:
        """detect_plan_mode behavior should be declared as an observer."""
        behaviors = {obs.behavior for obs in lifecycle_workflow.observers if obs.behavior}
        assert "detect_plan_mode" in behaviors

    def test_mcp_call_tracking_observer_declared(self, lifecycle_workflow: WorkflowDefinition) -> None:
        """mcp_call_tracking behavior should be declared as an observer."""
        behaviors = {obs.behavior for obs in lifecycle_workflow.observers if obs.behavior}
        assert "mcp_call_tracking" in behaviors

    def test_no_detect_plan_mode_trigger_action(self, lifecycle_data: dict) -> None:
        """detect_plan_mode_from_context trigger action should be removed (replaced by observer)."""
        before_agent_triggers = lifecycle_data.get("triggers", {}).get("on_before_agent", [])
        actions = [t.get("action") for t in before_agent_triggers]
        assert "detect_plan_mode_from_context" not in actions
