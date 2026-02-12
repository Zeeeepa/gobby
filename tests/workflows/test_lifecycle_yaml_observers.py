"""Tests for observer declarations in session-lifecycle.yaml.

Verifies: session-lifecycle.yaml declares behavior observers for
task_claim_tracking, detect_plan_mode, and mcp_call_tracking.
These observers replace hardcoded detect_* calls in lifecycle_evaluator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gobby.workflows.definitions import Observer, WorkflowDefinition

pytestmark = pytest.mark.unit

LIFECYCLE_YAML = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "gobby"
    / "install"
    / "shared"
    / "workflows"
    / "lifecycle"
    / "session-lifecycle.yaml"
)


class TestSessionLifecycleObservers:
    def test_yaml_loads_with_observers(self) -> None:
        """session-lifecycle.yaml should parse and include an observers field."""
        with open(LIFECYCLE_YAML) as f:
            data = yaml.safe_load(f)
        assert "observers" in data, "session-lifecycle.yaml should have an 'observers' field"
        assert len(data["observers"]) == 3

    def test_workflow_definition_parses_observers(self) -> None:
        """WorkflowDefinition should parse observers from session-lifecycle.yaml."""
        with open(LIFECYCLE_YAML) as f:
            data = yaml.safe_load(f)
        wf = WorkflowDefinition(**data)
        assert len(wf.observers) == 3

    def test_task_claim_tracking_observer_declared(self) -> None:
        """task_claim_tracking behavior should be declared as an observer."""
        with open(LIFECYCLE_YAML) as f:
            data = yaml.safe_load(f)
        wf = WorkflowDefinition(**data)
        behaviors = {obs.behavior for obs in wf.observers if obs.behavior}
        assert "task_claim_tracking" in behaviors

    def test_detect_plan_mode_observer_declared(self) -> None:
        """detect_plan_mode behavior should be declared as an observer."""
        with open(LIFECYCLE_YAML) as f:
            data = yaml.safe_load(f)
        wf = WorkflowDefinition(**data)
        behaviors = {obs.behavior for obs in wf.observers if obs.behavior}
        assert "detect_plan_mode" in behaviors

    def test_mcp_call_tracking_observer_declared(self) -> None:
        """mcp_call_tracking behavior should be declared as an observer."""
        with open(LIFECYCLE_YAML) as f:
            data = yaml.safe_load(f)
        wf = WorkflowDefinition(**data)
        behaviors = {obs.behavior for obs in wf.observers if obs.behavior}
        assert "mcp_call_tracking" in behaviors

    def test_no_detect_plan_mode_trigger_action(self) -> None:
        """detect_plan_mode_from_context trigger action should be removed (replaced by observer)."""
        with open(LIFECYCLE_YAML) as f:
            data = yaml.safe_load(f)
        # Check on_before_agent triggers don't contain detect_plan_mode_from_context
        before_agent_triggers = data.get("triggers", {}).get("on_before_agent", [])
        actions = [t.get("action") for t in before_agent_triggers]
        assert "detect_plan_mode_from_context" not in actions
