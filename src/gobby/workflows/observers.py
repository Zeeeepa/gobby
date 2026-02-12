"""Observer engine for YAML observer matching, variable setting, and behavior registry.

Evaluates Observer definitions against hook events and updates workflow
state variables when matches occur. Supports two observer variants:
- YAML observers: inline on/match/set definitions
- Behavior observers: delegate to registered Python callables
"""

import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from jinja2 import Environment

from gobby.workflows.definitions import Observer, WorkflowState

if TYPE_CHECKING:
    from gobby.hooks.events import HookEvent

logger = logging.getLogger(__name__)

# Shared Jinja2 environment for evaluating set expressions
_jinja_env = Environment()

# Type for behavior callables: async (event, state, **kwargs) -> None
BehaviorFn = Callable[..., Coroutine[Any, Any, None]]


class BehaviorRegistry:
    """Registry mapping behavior names to async Python callables.

    Tracks built-in behaviors separately from plugin-registered ones.
    Built-in behaviors cannot be overridden by plugins.
    """

    def __init__(self) -> None:
        self._behaviors: dict[str, BehaviorFn] = {}
        self._builtin_names: set[str] = set()

    def register(self, name: str, fn: BehaviorFn) -> None:
        """Register a built-in behavior by name."""
        self._behaviors[name] = fn
        self._builtin_names.add(name)

    def register_plugin_behavior(self, name: str, fn: BehaviorFn) -> None:
        """Register a plugin-provided behavior.

        Raises ValueError if the name conflicts with a built-in behavior
        or is already registered by another plugin.
        """
        if name in self._builtin_names:
            raise ValueError(
                f"Cannot register plugin behavior '{name}': conflicts with built-in behavior"
            )
        if name in self._behaviors:
            raise ValueError(
                f"Cannot register plugin behavior '{name}': already registered"
            )
        self._behaviors[name] = fn

    @property
    def builtin_names(self) -> set[str]:
        """Set of built-in behavior names (protected from plugin override)."""
        return set(self._builtin_names)

    def get(self, name: str) -> BehaviorFn | None:
        """Get a behavior by name, or None if not found."""
        return self._behaviors.get(name)

    def has(self, name: str) -> bool:
        """Check if a behavior is registered."""
        return name in self._behaviors

    def list(self) -> list[str]:
        """List all registered behavior names."""
        return list(self._behaviors.keys())


class ObserverEngine:
    """Evaluates YAML observers and behavior observers against events."""

    def __init__(self, behavior_registry: BehaviorRegistry | None = None) -> None:
        self._behavior_registry = behavior_registry

    async def evaluate_observers(
        self,
        observers: list[Observer],
        event_type: str,
        event_data: dict[str, Any],
        state: WorkflowState,
        event: "HookEvent | None" = None,
        **kwargs: Any,
    ) -> None:
        """Evaluate all observers against an event, updating state variables.

        Args:
            observers: List of Observer definitions to evaluate
            event_type: The event type string (e.g., "after_tool", "before_tool")
            event_data: Hook event data dict (tool_name, tool_input, etc.)
            state: Workflow state to update on match
            event: Full HookEvent (passed to behavior callables)
            **kwargs: Additional context passed to behavior callables
        """
        for obs in observers:
            if obs.behavior is not None:
                # Behavior observer — delegate to registry
                await self._evaluate_behavior(obs, event, state, **kwargs)
            else:
                # YAML observer — match and set
                self._evaluate_yaml_observer(obs, event_type, event_data, state)

    async def _evaluate_behavior(
        self,
        obs: Observer,
        event: "HookEvent | None",
        state: WorkflowState,
        **kwargs: Any,
    ) -> None:
        """Evaluate a behavior observer by delegating to the registry."""
        if self._behavior_registry is None:
            logger.debug(f"Observer '{obs.name}': no behavior registry, skipping")
            return

        fn = self._behavior_registry.get(obs.behavior or "")
        if fn is None:
            logger.warning(
                f"Observer '{obs.name}': behavior '{obs.behavior}' not found in registry"
            )
            return

        try:
            await fn(event, state, **kwargs)
        except Exception as e:
            logger.error(
                f"Observer '{obs.name}': behavior '{obs.behavior}' failed: {e}",
                exc_info=True,
            )

    def _evaluate_yaml_observer(
        self,
        obs: Observer,
        event_type: str,
        event_data: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        """Evaluate a YAML observer (on/match/set)."""
        if obs.on != event_type:
            return

        if not self._matches(obs, event_data):
            return

        if obs.set:
            self._apply_set(obs, event_data, state)

    def _matches(self, obs: Observer, event_data: dict[str, Any]) -> bool:
        """Check if observer match criteria are satisfied.

        All specified match fields must match (AND logic).
        If no match dict, matches everything.
        """
        if obs.match is None:
            return True

        tool_name = event_data.get("tool_name", "")
        tool_input = event_data.get("tool_input", {}) or {}

        # Check tool name match
        if "tool" in obs.match:
            if obs.match["tool"] != tool_name:
                return False

        # Check MCP server match
        if "mcp_server" in obs.match:
            server = tool_input.get("server_name") or tool_input.get("server") or ""
            if obs.match["mcp_server"] != server:
                return False

        # Check MCP tool match
        if "mcp_tool" in obs.match:
            tool = tool_input.get("tool_name") or tool_input.get("tool") or ""
            if obs.match["mcp_tool"] != tool:
                return False

        return True

    def _apply_set(
        self,
        obs: Observer,
        event_data: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        """Evaluate set expressions and update state variables."""
        if not obs.set:
            return

        for var_name, expression in obs.set.items():
            try:
                value = self._evaluate_expression(expression, event_data, state)
                state.variables[var_name] = value
            except Exception as e:
                logger.warning(
                    f"Observer '{obs.name}' failed to evaluate set expression "
                    f"for '{var_name}': {e}"
                )

    def _evaluate_expression(
        self,
        expression: str,
        event_data: dict[str, Any],
        state: WorkflowState,
    ) -> Any:
        """Evaluate a set expression (Jinja2 template or literal).

        Returns the coerced value — booleans, None, numbers are converted
        from their string representations to native Python types.
        """
        # If it contains Jinja2 template markers, render as template
        if "{{" in expression:
            template = _jinja_env.from_string(expression)
            context = {
                "variables": state.variables,
                "event_data": event_data,
            }
            raw = template.render(**context)
        else:
            # Otherwise treat as literal value
            raw = expression

        return self._coerce_value(raw)

    @staticmethod
    def _coerce_value(raw: str) -> Any:
        """Coerce string literals to native Python types.

        Converts "true"/"false" to bool, "null"/"none" to None,
        and numeric strings to int/float. Unrecognized strings
        pass through unchanged.
        """
        lower = raw.strip().lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        if lower in ("null", "none"):
            return None
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        return raw


# =============================================================================
# Built-in behaviors
# =============================================================================


async def _task_claim_tracking(
    event: "HookEvent | None",
    state: WorkflowState,
    **kwargs: Any,
) -> None:
    """Behavior: track task claims/releases via detect_task_claim.

    Wraps the existing detect_task_claim function from detection_helpers.
    """
    if event is None:
        return

    from gobby.workflows.detection_helpers import detect_task_claim

    task_manager = kwargs.get("task_manager")
    session_task_manager = kwargs.get("session_task_manager")
    detect_task_claim(
        event=event,
        state=state,
        session_task_manager=session_task_manager,
        task_manager=task_manager,
    )


async def _detect_plan_mode(
    event: "HookEvent | None",
    state: WorkflowState,
    **kwargs: Any,
) -> None:
    """Behavior: detect plan mode from system-reminder tags.

    Wraps the existing detect_plan_mode_from_context function.
    """
    if event is None or not event.data:
        return

    from gobby.workflows.detection_helpers import detect_plan_mode_from_context

    prompt = event.data.get("prompt", "") or ""
    detect_plan_mode_from_context(prompt, state)


async def _mcp_call_tracking(
    event: "HookEvent | None",
    state: WorkflowState,
    **kwargs: Any,
) -> None:
    """Behavior: track MCP tool calls in state variables.

    Wraps the existing detect_mcp_call function.
    """
    if event is None:
        return

    from gobby.workflows.detection_helpers import detect_mcp_call

    detect_mcp_call(event, state)


def get_default_registry() -> BehaviorRegistry:
    """Create a BehaviorRegistry with all built-in behaviors registered."""
    registry = BehaviorRegistry()
    registry.register("task_claim_tracking", _task_claim_tracking)
    registry.register("detect_plan_mode", _detect_plan_mode)
    registry.register("mcp_call_tracking", _mcp_call_tracking)
    return registry
