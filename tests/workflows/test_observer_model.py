"""Tests for Observer model and observers field on WorkflowDefinition.

Verifies: Observer model validates YAML observers (on/match/set) and
behavior refs (behavior field). WorkflowDefinition accepts observers list.
"""

from __future__ import annotations

import pytest

from gobby.workflows.definitions import WorkflowDefinition

pytestmark = pytest.mark.unit


class TestObserverYAMLVariant:
    """YAML observer: on/match/set fields."""

    def test_yaml_observer_creation(self) -> None:
        """Observer with on/match/set is valid."""
        from gobby.workflows.definitions import Observer

        obs = Observer(
            name="track_edits",
            on="after_tool",
            match={"tool": "Edit"},
            set={"files_edited": "files_edited + 1"},
        )
        assert obs.name == "track_edits"
        assert obs.on == "after_tool"
        assert obs.match == {"tool": "Edit"}
        assert obs.set == {"files_edited": "files_edited + 1"}
        assert obs.behavior is None

    def test_yaml_observer_with_mcp_match(self) -> None:
        """Observer can match on mcp_server and mcp_tool."""
        from gobby.workflows.definitions import Observer

        obs = Observer(
            name="track_task_claims",
            on="after_tool",
            match={"mcp_server": "gobby-tasks", "mcp_tool": "claim_task"},
            set={"task_claimed": "true"},
        )
        assert obs.match["mcp_server"] == "gobby-tasks"
        assert obs.match["mcp_tool"] == "claim_task"

    def test_yaml_observer_minimal(self) -> None:
        """Observer with just on and set (no match) is valid — matches all events of that type."""
        from gobby.workflows.definitions import Observer

        obs = Observer(
            name="count_all_tools",
            on="after_tool",
            set={"tool_count": "tool_count + 1"},
        )
        assert obs.on == "after_tool"
        assert obs.match is None
        assert obs.set == {"tool_count": "tool_count + 1"}


class TestObserverBehaviorVariant:
    """Behavior ref: behavior field."""

    def test_behavior_ref_creation(self) -> None:
        """Observer with behavior field is valid."""
        from gobby.workflows.definitions import Observer

        obs = Observer(
            name="task_tracking",
            behavior="task_claim_tracking",
        )
        assert obs.name == "task_tracking"
        assert obs.behavior == "task_claim_tracking"
        assert obs.on is None
        assert obs.match is None
        assert obs.set is None


class TestObserverValidation:
    """Validation: exactly one variant."""

    def test_rejects_both_behavior_and_on(self) -> None:
        """Observer with both behavior and on/set should be rejected."""
        from gobby.workflows.definitions import Observer

        with pytest.raises(ValueError, match="exactly one"):
            Observer(
                name="invalid",
                behavior="task_claim_tracking",
                on="after_tool",
                set={"x": "1"},
            )

    def test_rejects_neither_behavior_nor_on(self) -> None:
        """Observer with neither behavior nor on should be rejected."""
        from gobby.workflows.definitions import Observer

        with pytest.raises(ValueError, match="exactly one"):
            Observer(name="invalid")

    def test_rejects_behavior_with_match(self) -> None:
        """Observer with behavior and match should be rejected."""
        from gobby.workflows.definitions import Observer

        with pytest.raises(ValueError, match="exactly one"):
            Observer(
                name="invalid",
                behavior="task_claim_tracking",
                match={"tool": "Edit"},
            )


class TestWorkflowDefinitionObservers:
    """WorkflowDefinition.observers field."""

    def test_default_empty(self) -> None:
        """WorkflowDefinition.observers defaults to empty list."""
        defn = WorkflowDefinition(name="test", type="lifecycle")
        assert defn.observers == []

    def test_accepts_observer_list(self) -> None:
        """WorkflowDefinition accepts a list of Observer objects."""
        from gobby.workflows.definitions import Observer

        observers = [
            Observer(name="track_edits", on="after_tool", set={"edited": "true"}),
            Observer(name="task_tracking", behavior="task_claim_tracking"),
        ]
        defn = WorkflowDefinition(name="test", type="lifecycle", observers=observers)
        assert len(defn.observers) == 2
        assert defn.observers[0].name == "track_edits"
        assert defn.observers[1].behavior == "task_claim_tracking"

    def test_yaml_roundtrip_with_observers(self) -> None:
        """WorkflowDefinition with observers can be serialized and deserialized."""
        from gobby.workflows.definitions import Observer

        observers = [
            Observer(
                name="track_claims",
                on="after_tool",
                match={"mcp_tool": "claim_task"},
                set={"task_claimed": "true"},
            ),
        ]
        defn = WorkflowDefinition(name="test", type="lifecycle", observers=observers)
        data = defn.model_dump()
        restored = WorkflowDefinition(**data)
        assert len(restored.observers) == 1
        assert restored.observers[0].name == "track_claims"
        assert restored.observers[0].on == "after_tool"
        assert restored.observers[0].match == {"mcp_tool": "claim_task"}
