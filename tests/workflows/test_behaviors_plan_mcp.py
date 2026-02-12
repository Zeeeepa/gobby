"""Tests for detect_plan_mode and mcp_call_tracking behaviors.

Verifies: detect_plan_mode sets plan_mode from system-reminder tags,
mcp_call_tracking records MCP calls in state variables.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import WorkflowState

pytestmark = pytest.mark.unit


def _make_state(session_id: str = "test-session", **variables: Any) -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        workflow_name="test-wf",
        step="working",
        step_entered_at=datetime.now(UTC),
        variables=dict(variables),
    )


def _make_event(
    event_type: HookEventType = HookEventType.BEFORE_AGENT,
    data: dict[str, Any] | None = None,
) -> HookEvent:
    return HookEvent(
        event_type=event_type,
        session_id="ext-123",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data or {},
        metadata={"_platform_session_id": "test-session"},
    )


# =============================================================================
# detect_plan_mode behavior
# =============================================================================


class TestDetectPlanModeBehavior:
    @pytest.mark.asyncio
    async def test_registered_in_default_registry(self) -> None:
        """detect_plan_mode should be in the default registry."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()
        assert registry.has("detect_plan_mode")

    @pytest.mark.asyncio
    async def test_sets_plan_mode_true(self) -> None:
        """Sets plan_mode=True when system-reminder contains plan mode indicator."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("detect_plan_mode")
        assert behavior is not None

        state = _make_state()
        event = _make_event(
            event_type=HookEventType.BEFORE_AGENT,
            data={"prompt": "<system-reminder>Plan mode is active</system-reminder>"},
        )

        await behavior(event, state)

        assert state.variables.get("plan_mode") is True

    @pytest.mark.asyncio
    async def test_sets_plan_mode_false_on_exit(self) -> None:
        """Sets plan_mode=False when system-reminder contains exit indicator."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("detect_plan_mode")
        assert behavior is not None

        state = _make_state(plan_mode=True)
        event = _make_event(
            event_type=HookEventType.BEFORE_AGENT,
            data={"prompt": "<system-reminder>Exited Plan Mode</system-reminder>"},
        )

        await behavior(event, state)

        assert state.variables.get("plan_mode") is False

    @pytest.mark.asyncio
    async def test_ignores_non_system_reminder(self) -> None:
        """Does not set plan_mode from text outside system-reminder tags."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("detect_plan_mode")
        assert behavior is not None

        state = _make_state()
        event = _make_event(
            event_type=HookEventType.BEFORE_AGENT,
            data={"prompt": "The user mentioned Plan mode is active in their message"},
        )

        await behavior(event, state)

        assert "plan_mode" not in state.variables

    @pytest.mark.asyncio
    async def test_handles_empty_prompt(self) -> None:
        """Does nothing on empty prompt."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("detect_plan_mode")
        assert behavior is not None

        state = _make_state()
        event = _make_event(data={"prompt": ""})

        await behavior(event, state)

        assert "plan_mode" not in state.variables


# =============================================================================
# mcp_call_tracking behavior
# =============================================================================


class TestMCPCallTrackingBehavior:
    @pytest.mark.asyncio
    async def test_registered_in_default_registry(self) -> None:
        """mcp_call_tracking should be in the default registry."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()
        assert registry.has("mcp_call_tracking")

    @pytest.mark.asyncio
    async def test_records_mcp_call(self) -> None:
        """Records successful MCP call in mcp_calls state variable."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("mcp_call_tracking")
        assert behavior is not None

        state = _make_state()
        event = _make_event(
            event_type=HookEventType.AFTER_TOOL,
            data={
                "tool_name": "mcp__gobby__call_tool",
                "mcp_server": "gobby-memory",
                "mcp_tool": "search_memories",
                "tool_output": {"result": {"memories": []}},
            },
        )

        await behavior(event, state)

        mcp_calls = state.variables.get("mcp_calls", {})
        assert "gobby-memory" in mcp_calls
        assert "search_memories" in mcp_calls["gobby-memory"]

    @pytest.mark.asyncio
    async def test_handles_missing_mcp_fields(self) -> None:
        """Does nothing when mcp_server/mcp_tool are missing."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("mcp_call_tracking")
        assert behavior is not None

        state = _make_state()
        event = _make_event(
            event_type=HookEventType.AFTER_TOOL,
            data={"tool_name": "Edit", "tool_input": {}},
        )

        await behavior(event, state)

        assert "mcp_calls" not in state.variables

    @pytest.mark.asyncio
    async def test_skips_error_responses(self) -> None:
        """Does not track MCP calls that returned errors."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("mcp_call_tracking")
        assert behavior is not None

        state = _make_state()
        event = _make_event(
            event_type=HookEventType.AFTER_TOOL,
            data={
                "tool_name": "mcp__gobby__call_tool",
                "mcp_server": "gobby-tasks",
                "mcp_tool": "get_task",
                "tool_output": {"error": "Task not found"},
            },
        )

        await behavior(event, state)

        # Error calls should not be tracked
        mcp_calls = state.variables.get("mcp_calls", {})
        assert "gobby-tasks" not in mcp_calls

    @pytest.mark.asyncio
    async def test_handles_none_event(self) -> None:
        """Does nothing when event is None."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("mcp_call_tracking")
        assert behavior is not None

        state = _make_state()
        await behavior(None, state)

        assert "mcp_calls" not in state.variables
