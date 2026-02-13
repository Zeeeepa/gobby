"""Tests for ObserverEngine: YAML observer matching and variable setting.

Verifies: observers match by tool name, mcp_server/mcp_tool, set variables
on match, AND logic for multiple match criteria, non-matching skipped,
arithmetic expressions, multiple observers fire on same event.
"""

from __future__ import annotations

from typing import Any

import pytest

from gobby.workflows.definitions import Observer, WorkflowState
from gobby.workflows.observers import ObserverEngine

pytestmark = pytest.mark.unit


def _make_state(**variables: Any) -> WorkflowState:
    """Create a WorkflowState with given variables."""
    from datetime import UTC, datetime

    return WorkflowState(
        session_id="test-session",
        workflow_name="test-wf",
        step="working",
        step_entered_at=datetime.now(UTC),
        variables=dict(variables),
    )


def _make_event_data(
    tool_name: str = "Edit",
    tool_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create event data dict as it appears in HookEvent.data."""
    return {
        "tool_name": tool_name,
        "tool_input": tool_input or {},
    }


class TestObserverMatchByTool:
    @pytest.mark.asyncio
    async def test_matches_by_tool_name(self) -> None:
        """Observer with match.tool should match event tool_name."""
        obs = Observer(
            name="track_edits",
            on="after_tool",
            match={"tool": "Edit"},
            set={"edited": "true"},
        )
        state = _make_state()
        event_data = _make_event_data(tool_name="Edit")

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", event_data, state)

        assert state.variables["edited"] is True

    @pytest.mark.asyncio
    async def test_non_matching_tool_skipped(self) -> None:
        """Observer should not fire when tool doesn't match."""
        obs = Observer(
            name="track_writes",
            on="after_tool",
            match={"tool": "Write"},
            set={"wrote": "true"},
        )
        state = _make_state()
        event_data = _make_event_data(tool_name="Edit")

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", event_data, state)

        assert "wrote" not in state.variables


class TestObserverMatchByMCP:
    @pytest.mark.asyncio
    async def test_matches_by_mcp_server_and_tool(self) -> None:
        """Observer with mcp_server+mcp_tool should match MCP call_tool events."""
        obs = Observer(
            name="track_claims",
            on="after_tool",
            match={"mcp_server": "gobby-tasks", "mcp_tool": "claim_task"},
            set={"task_claimed": "true"},
        )
        state = _make_state()
        event_data = _make_event_data(
            tool_name="mcp__gobby__call_tool",
            tool_input={"server_name": "gobby-tasks", "tool_name": "claim_task"},
        )

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", event_data, state)

        assert state.variables["task_claimed"] is True

    @pytest.mark.asyncio
    async def test_mcp_server_mismatch_skipped(self) -> None:
        """Observer should not fire when mcp_server doesn't match."""
        obs = Observer(
            name="track_claims",
            on="after_tool",
            match={"mcp_server": "gobby-tasks", "mcp_tool": "claim_task"},
            set={"task_claimed": "true"},
        )
        state = _make_state()
        event_data = _make_event_data(
            tool_name="mcp__gobby__call_tool",
            tool_input={"server_name": "gobby-memory", "tool_name": "create_memory"},
        )

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", event_data, state)

        assert "task_claimed" not in state.variables


class TestObserverMatchAND:
    @pytest.mark.asyncio
    async def test_all_match_criteria_must_pass(self) -> None:
        """Multiple match fields use AND logic — all must match."""
        obs = Observer(
            name="track_specific",
            on="after_tool",
            match={"tool": "mcp__gobby__call_tool", "mcp_server": "gobby-tasks"},
            set={"matched": "true"},
        )
        state = _make_state()
        # tool matches but mcp_server doesn't (different server)
        event_data = _make_event_data(
            tool_name="mcp__gobby__call_tool",
            tool_input={"server_name": "gobby-memory", "tool_name": "search"},
        )

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", event_data, state)

        assert "matched" not in state.variables


class TestObserverNoMatch:
    @pytest.mark.asyncio
    async def test_no_match_field_matches_all(self) -> None:
        """Observer with no match field matches all events of the right type."""
        obs = Observer(
            name="count_all",
            on="after_tool",
            set={"tool_used": "true"},
        )
        state = _make_state()
        event_data = _make_event_data(tool_name="anything")

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", event_data, state)

        assert state.variables["tool_used"] is True


class TestObserverSetExpressions:
    @pytest.mark.asyncio
    async def test_literal_string_value(self) -> None:
        """Set expression with a plain string literal stays as string."""
        obs = Observer(
            name="set_name",
            on="after_tool",
            set={"name": "hello"},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["name"] == "hello"

    @pytest.mark.asyncio
    async def test_arithmetic_expression(self) -> None:
        """Set expression with Jinja2 arithmetic template coerces to int."""
        obs = Observer(
            name="count_edits",
            on="after_tool",
            match={"tool": "Edit"},
            set={"edit_count": "{{ (variables.edit_count or 0) + 1 }}"},
        )
        state = _make_state(edit_count=5)

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data("Edit"), state)

        assert state.variables["edit_count"] == 6
        assert isinstance(state.variables["edit_count"], int)


class TestObserverTypeCoercion:
    """Tests for _coerce_value: YAML observer set values are coerced to native types."""

    @pytest.mark.asyncio
    async def test_true_coerced_to_bool(self) -> None:
        """Literal 'true' should be coerced to Python True."""
        obs = Observer(
            name="set_flag",
            on="after_tool",
            set={"task_claimed": "true"},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["task_claimed"] is True

    @pytest.mark.asyncio
    async def test_false_coerced_to_bool(self) -> None:
        """Literal 'false' should be coerced to Python False."""
        obs = Observer(
            name="clear_flag",
            on="after_tool",
            set={"task_claimed": "false"},
        )
        state = _make_state(task_claimed=True)

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["task_claimed"] is False

    @pytest.mark.asyncio
    async def test_null_coerced_to_none(self) -> None:
        """Literal 'null' should be coerced to Python None."""
        obs = Observer(
            name="clear_value",
            on="after_tool",
            set={"session_task": "null"},
        )
        state = _make_state(session_task="#123")

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["session_task"] is None

    @pytest.mark.asyncio
    async def test_none_coerced_to_none(self) -> None:
        """Literal 'none' should be coerced to Python None."""
        obs = Observer(
            name="clear_value",
            on="after_tool",
            set={"val": "none"},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["val"] is None

    @pytest.mark.asyncio
    async def test_integer_coerced(self) -> None:
        """Literal '42' should be coerced to int 42."""
        obs = Observer(
            name="set_count",
            on="after_tool",
            set={"count": "42"},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["count"] == 42
        assert isinstance(state.variables["count"], int)

    @pytest.mark.asyncio
    async def test_float_coerced(self) -> None:
        """Literal '3.14' should be coerced to float 3.14."""
        obs = Observer(
            name="set_ratio",
            on="after_tool",
            set={"ratio": "3.14"},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["ratio"] == 3.14
        assert isinstance(state.variables["ratio"], float)

    @pytest.mark.asyncio
    async def test_jinja2_true_result_coerced(self) -> None:
        """Jinja2 template rendering 'True' should be coerced to bool True."""
        obs = Observer(
            name="check_flag",
            on="after_tool",
            set={"is_active": "{{ 'true' if variables.count else 'false' }}"},
        )
        state = _make_state(count=5)

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["is_active"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("val", ["True", "TRUE", " true "])
    async def test_case_insensitive_coercion(self, val: str) -> None:
        """'True', 'TRUE', ' true ' should all coerce to bool True."""
        obs = Observer(
            name="set_flag",
            on="after_tool",
            set={"flag": val},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert state.variables["flag"] is True, f"Expected True for {val!r}"


class TestObserverEventTypeFilter:
    @pytest.mark.asyncio
    async def test_wrong_event_type_skipped(self) -> None:
        """Observer with on='after_tool' should not fire on 'before_tool'."""
        obs = Observer(
            name="after_only",
            on="after_tool",
            set={"fired": "true"},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers([obs], "before_tool", _make_event_data(), state)

        assert "fired" not in state.variables


class TestMultipleObservers:
    @pytest.mark.asyncio
    async def test_multiple_observers_fire_on_same_event(self) -> None:
        """Multiple matching observers should all fire."""
        obs1 = Observer(
            name="track_tool",
            on="after_tool",
            set={"tool_tracked": "true"},
        )
        obs2 = Observer(
            name="count_tool",
            on="after_tool",
            set={"tool_counted": "true"},
        )
        state = _make_state()

        engine = ObserverEngine()
        await engine.evaluate_observers(
            [obs1, obs2], "after_tool", _make_event_data(), state
        )

        assert state.variables["tool_tracked"] is True
        assert state.variables["tool_counted"] is True


class TestBehaviorObserverSkipped:
    @pytest.mark.asyncio
    async def test_behavior_observer_skipped_by_yaml_engine(self) -> None:
        """Behavior observers should be skipped by evaluate_observers (handled elsewhere)."""
        obs = Observer(name="task_tracking", behavior="task_claim_tracking")
        state = _make_state()

        engine = ObserverEngine()
        # Should not raise or modify state
        await engine.evaluate_observers([obs], "after_tool", _make_event_data(), state)

        assert len(state.variables) == 0
