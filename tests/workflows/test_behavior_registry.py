"""Tests for BehaviorRegistry and task_claim_tracking behavior.

Verifies: BehaviorRegistry registers/retrieves/lists behaviors,
task_claim_tracking behavior wraps detect_task_claim correctly,
ObserverEngine evaluates behavior observers via the registry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import Observer, WorkflowState

pytestmark = pytest.mark.unit


def _make_state(session_id: str = "test-session", **variables: Any) -> WorkflowState:
    """Create a WorkflowState with given variables."""
    return WorkflowState(
        session_id=session_id,
        workflow_name="test-wf",
        step="working",
        step_entered_at=datetime.now(UTC),
        variables=dict(variables),
    )


def _make_event(
    tool_name: str = "mcp__gobby__call_tool",
    tool_input: dict[str, Any] | None = None,
    tool_output: dict[str, Any] | None = None,
    mcp_server: str = "",
    mcp_tool: str = "",
) -> HookEvent:
    """Create an AFTER_TOOL HookEvent."""
    data: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_input": tool_input or {},
    }
    if tool_output is not None:
        data["tool_output"] = tool_output
    if mcp_server:
        data["mcp_server"] = mcp_server
    if mcp_tool:
        data["mcp_tool"] = mcp_tool
    return HookEvent(
        event_type=HookEventType.AFTER_TOOL,
        session_id="ext-session-123",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data,
        metadata={"_platform_session_id": "test-session"},
    )


# =============================================================================
# BehaviorRegistry
# =============================================================================


class TestBehaviorRegistry:
    def test_register_and_get(self) -> None:
        """Register a behavior and retrieve it by name."""
        from gobby.workflows.observers import BehaviorRegistry

        registry = BehaviorRegistry()

        async def my_behavior(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        registry.register("my_behavior", my_behavior)
        assert registry.get("my_behavior") is my_behavior

    def test_get_unknown_returns_none(self) -> None:
        """Getting unknown behavior returns None."""
        from gobby.workflows.observers import BehaviorRegistry

        registry = BehaviorRegistry()
        assert registry.get("nonexistent") is None

    def test_list_behaviors(self) -> None:
        """List all registered behavior names."""
        from gobby.workflows.observers import BehaviorRegistry

        registry = BehaviorRegistry()

        async def b1(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        async def b2(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        registry.register("alpha", b1)
        registry.register("beta", b2)
        names = registry.list()
        assert "alpha" in names
        assert "beta" in names

    def test_has_behavior(self) -> None:
        """Check if a behavior is registered."""
        from gobby.workflows.observers import BehaviorRegistry

        registry = BehaviorRegistry()

        async def b(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        registry.register("exists", b)
        assert registry.has("exists") is True
        assert registry.has("missing") is False


# =============================================================================
# task_claim_tracking behavior
# =============================================================================


class TestTaskClaimTrackingBehavior:
    @pytest.mark.asyncio
    async def test_sets_task_claimed_on_claim_task(self) -> None:
        """task_claim_tracking sets task_claimed=True on successful claim_task."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()
        assert registry.has("task_claim_tracking")

        behavior = registry.get("task_claim_tracking")
        assert behavior is not None

        state = _make_state()
        task_manager = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "uuid-123"
        task_manager.get_task.return_value = mock_task

        event = _make_event(
            mcp_server="gobby-tasks",
            mcp_tool="claim_task",
            tool_input={"arguments": {"task_id": "#42"}},
            tool_output={"result": {"status": "ok"}},
        )

        await behavior(event, state, task_manager=task_manager)

        assert state.variables.get("task_claimed") is True
        assert state.variables.get("claimed_task_id") == "uuid-123"

    @pytest.mark.asyncio
    async def test_clears_task_claimed_on_close_task(self) -> None:
        """task_claim_tracking clears task_claimed on successful close_task."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()
        behavior = registry.get("task_claim_tracking")
        assert behavior is not None

        state = _make_state(task_claimed=True, claimed_task_id="uuid-123")
        event = _make_event(
            mcp_server="gobby-tasks",
            mcp_tool="close_task",
            tool_output={"result": {"status": "ok"}},
        )

        await behavior(event, state)

        assert state.variables.get("task_claimed") is False
        assert state.variables.get("claimed_task_id") is None

    @pytest.mark.asyncio
    async def test_handles_error_response(self) -> None:
        """task_claim_tracking does nothing on error responses."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("task_claim_tracking")
        assert behavior is not None

        state = _make_state()
        event = _make_event(
            mcp_server="gobby-tasks",
            mcp_tool="claim_task",
            tool_input={"arguments": {"task_id": "#42"}},
            tool_output={"error": "Task not found"},
        )

        await behavior(event, state)

        assert "task_claimed" not in state.variables

    @pytest.mark.asyncio
    async def test_skips_non_gobby_tasks(self) -> None:
        """task_claim_tracking ignores non-gobby-tasks MCP calls."""
        from gobby.workflows.observers import get_default_registry

        behavior = get_default_registry().get("task_claim_tracking")
        assert behavior is not None

        state = _make_state()
        event = _make_event(
            mcp_server="gobby-memory",
            mcp_tool="create_memory",
        )

        await behavior(event, state)

        assert "task_claimed" not in state.variables


# =============================================================================
# ObserverEngine with behavior observers
# =============================================================================


class TestObserverEngineWithBehaviors:
    @pytest.mark.asyncio
    async def test_evaluate_behavior_observer(self) -> None:
        """ObserverEngine evaluates behavior observers via registry."""
        from gobby.workflows.observers import BehaviorRegistry, ObserverEngine

        called_with: dict[str, Any] = {}

        async def mock_behavior(event: Any, state: Any, **kwargs: Any) -> None:
            called_with["event"] = event
            called_with["state"] = state
            state.variables["behavior_fired"] = True

        registry = BehaviorRegistry()
        registry.register("test_behavior", mock_behavior)

        obs = Observer(name="test", behavior="test_behavior")
        state = _make_state()
        event = _make_event()

        engine = ObserverEngine(behavior_registry=registry)
        await engine.evaluate_observers([obs], "after_tool", event.data, state, event=event)

        assert state.variables.get("behavior_fired") is True
        assert called_with["state"] is state

    @pytest.mark.asyncio
    async def test_unknown_behavior_skipped(self) -> None:
        """Unknown behavior name is skipped without error."""
        from gobby.workflows.observers import BehaviorRegistry, ObserverEngine

        registry = BehaviorRegistry()
        obs = Observer(name="unknown", behavior="nonexistent")
        state = _make_state()
        event = _make_event()

        engine = ObserverEngine(behavior_registry=registry)
        # Should not raise
        await engine.evaluate_observers([obs], "after_tool", event.data, state, event=event)

        assert len(state.variables) == 0


# =============================================================================
# Plugin behavior registration
# =============================================================================


class TestPluginBehaviorRegistration:
    """Tests for register_plugin_behavior and built-in protection."""

    def test_register_plugin_behavior_adds_to_registry(self) -> None:
        """register_plugin_behavior adds a custom behavior to the registry."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()

        async def custom_behavior(event: Any, state: Any, **kwargs: Any) -> None:
            state.variables["custom_fired"] = True

        registry.register_plugin_behavior("my_plugin_behavior", custom_behavior)
        assert registry.has("my_plugin_behavior")
        assert registry.get("my_plugin_behavior") is custom_behavior

    def test_plugin_behavior_listed(self) -> None:
        """Plugin behaviors appear in list() alongside built-ins."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()

        async def custom(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        registry.register_plugin_behavior("custom_plugin", custom)
        names = registry.list()
        assert "custom_plugin" in names
        assert "task_claim_tracking" in names  # built-in still present

    def test_override_builtin_raises_error(self) -> None:
        """Registering a plugin behavior with a built-in name raises ValueError."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()

        async def override_fn(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        with pytest.raises(ValueError, match="built-in"):
            registry.register_plugin_behavior("task_claim_tracking", override_fn)

    def test_duplicate_plugin_behavior_raises_error(self) -> None:
        """Registering two plugin behaviors with the same name raises ValueError."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()

        async def plugin_a(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        async def plugin_b(event: Any, state: Any, **kwargs: Any) -> None:
            pass

        registry.register_plugin_behavior("unique_plugin", plugin_a)
        with pytest.raises(ValueError, match="already registered"):
            registry.register_plugin_behavior("unique_plugin", plugin_b)

    @pytest.mark.asyncio
    async def test_plugin_behavior_callable_from_observer(self) -> None:
        """Plugin behavior is invoked via ObserverEngine when observer references it."""
        from gobby.workflows.observers import ObserverEngine, get_default_registry

        registry = get_default_registry()
        call_log: list[str] = []

        async def tracking_behavior(event: Any, state: Any, **kwargs: Any) -> None:
            call_log.append("called")
            state.variables["plugin_ran"] = True

        registry.register_plugin_behavior("tracking_plugin", tracking_behavior)

        obs = Observer(name="plugin_obs", behavior="tracking_plugin")
        state = _make_state()
        event = _make_event()

        engine = ObserverEngine(behavior_registry=registry)
        await engine.evaluate_observers([obs], "after_tool", event.data, state, event=event)

        assert call_log == ["called"]
        assert state.variables.get("plugin_ran") is True

    def test_builtin_names_property(self) -> None:
        """Registry exposes set of built-in behavior names."""
        from gobby.workflows.observers import get_default_registry

        registry = get_default_registry()
        builtins = registry.builtin_names
        assert "task_claim_tracking" in builtins
        assert "detect_plan_mode" in builtins
        assert "mcp_call_tracking" in builtins
