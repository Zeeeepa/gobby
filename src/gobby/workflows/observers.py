"""Observer engine for YAML observer matching, variable setting, and behavior registry.

Evaluates Observer definitions against hook events and updates workflow
state variables when matches occur. Supports two observer variants:
- YAML observers: inline on/match/set definitions
- Behavior observers: delegate to registered Python callables

Also contains detection functions (previously in detection_helpers.py)
for task claims, plan mode, and MCP call tracking.
"""

import logging
import re
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from jinja2.sandbox import SandboxedEnvironment

from gobby.workflows.definitions import Observer, WorkflowState

if TYPE_CHECKING:
    from gobby.hooks.events import HookEvent
    from gobby.storage.tasks import LocalTaskManager
    from gobby.tasks.session_tasks import SessionTaskManager

logger = logging.getLogger(__name__)

# Shared Jinja2 environment for evaluating set expressions
_jinja_env = SandboxedEnvironment()

# Type for behavior callables: async (event, state, **kwargs) -> None
BehaviorFn = Callable[..., Coroutine[Any, Any, None]]


_MODE_LEVEL_MAP = {"plan": 0, "accept_edits": 1, "normal": 1, "bypass": 2}


def compute_mode_level(chat_mode: str) -> int:
    """Derive numeric mode_level from chat_mode.

    Returns 0 (Plan), 1 (Act), or 2 (Full Auto).
    """
    return _MODE_LEVEL_MAP.get(chat_mode, 2)


# =============================================================================
# Detection functions
# =============================================================================


def detect_task_claim(
    event: "HookEvent",
    state: "WorkflowState",
    session_task_manager: "SessionTaskManager | None" = None,
    task_manager: "LocalTaskManager | None" = None,
) -> None:
    """Detect gobby-tasks calls that claim or release a task for this session.

    Sets `task_claimed: true` in workflow state variables when the agent
    successfully creates a task or updates a task to in_progress status.

    Clears `task_claimed: false` when the agent closes a task, requiring
    them to claim another task before making further file modifications.

    This enables session-scoped task enforcement where each session must
    explicitly claim a task rather than free-riding on project-wide checks.

    Args:
        event: The AFTER_TOOL hook event
        state: Current workflow state (modified in place)
        session_task_manager: Optional manager for auto-linking tasks to sessions
    """
    if not event.data:
        return

    tool_input = event.data.get("tool_input", {}) or {}
    # Use normalized tool_output (adapters normalize tool_result/tool_response)
    tool_output = event.data.get("tool_output") or {}

    # Use normalized MCP fields from adapter layer
    # Adapters extract these from CLI-specific formats
    server_name = event.data.get("mcp_server", "")
    if server_name != "gobby-tasks":
        return

    inner_tool_name = event.data.get("mcp_tool", "")

    # Handle close_task - clears task_claimed when task is closed
    # Note: Claude Code doesn't include tool_result in post-tool-use hooks, so for CC
    # the workflow state is updated directly in the MCP proxy's close_task function.
    # This detection provides a fallback for CLIs that do report tool results (Gemini/Codex).
    if inner_tool_name == "close_task":
        # tool_output already normalized at top of function

        # If no tool output, skip - can't verify success
        # The MCP proxy's close_task handles state clearing for successful closes
        if not tool_output:
            return

        # Check if close succeeded (not an error)
        if isinstance(tool_output, dict):
            if tool_output.get("error") or tool_output.get("status") == "error":
                return
            result = tool_output.get("result", {})
            if isinstance(result, dict) and result.get("error"):
                return

        # Clear task_claimed on successful close
        state.variables["task_claimed"] = False
        state.variables["claimed_task_id"] = None
        logger.info(f"Session {state.session_id}: task_claimed=False (detected close_task success)")
        return

    if inner_tool_name not in ("create_task", "update_task", "claim_task"):
        return

    # For update_task, only count if status is being set to in_progress
    if inner_tool_name == "update_task":
        arguments = tool_input.get("arguments", {}) or {}
        if arguments.get("status") != "in_progress":
            return
    # claim_task always counts (it sets status to in_progress internally)

    # Check if the call succeeded (not an error) - for non-close_task operations
    # tool_output structure varies, but errors typically have "error" key
    # or the MCP response has "status": "error"
    if isinstance(tool_output, dict):
        if tool_output.get("error") or tool_output.get("status") == "error":
            return
        # Also check nested result for MCP proxy responses
        result = tool_output.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            return

    # Extract task_id based on tool type - MUST resolve to UUID
    # Refs like '#123' will fail comparison with task.id (UUID) in close_task logic
    arguments = tool_input.get("arguments", {}) or {}
    task_id: str | None = None

    if inner_tool_name in ("update_task", "claim_task"):
        raw_task_id = arguments.get("task_id")
        # MUST resolve to UUID - refs like '#123' break comparisons in close_task
        if raw_task_id and task_manager:
            try:
                task = task_manager.get_task(raw_task_id)
                if task:
                    task_id = task.id  # Use UUID
                else:
                    logger.warning(
                        f"Cannot resolve task ref '{raw_task_id}' to UUID - task not found"
                    )
            except Exception as e:
                logger.warning(f"Cannot resolve task ref '{raw_task_id}' to UUID: {e}")
        elif raw_task_id and not task_manager:
            logger.warning(f"Cannot resolve task ref '{raw_task_id}' to UUID - no task_manager")
    elif inner_tool_name == "create_task":
        # For create_task, the id is in the result (already a UUID)
        result = tool_output.get("result", {}) if isinstance(tool_output, dict) else {}
        task_id = result.get("id") if isinstance(result, dict) else None
        # Skip if we can't get the task ID (e.g., Claude Code doesn't include tool results)
        # The MCP tool itself handles state updates in this case via _crud.py
        if not task_id:
            return

    # Only set claimed_task_id if we have a valid UUID
    if not task_id:
        logger.debug(f"Skipping task claim state update - no valid UUID for {inner_tool_name}")
        return

    # All conditions met - set task_claimed and claimed_task_id (UUID)
    state.variables["task_claimed"] = True
    state.variables["claimed_task_id"] = task_id
    state.variables["session_had_task"] = True
    logger.info(
        f"Session {state.session_id}: task_claimed=True, claimed_task_id={task_id} "
        f"(via {inner_tool_name})"
    )

    # Auto-link task to session when claiming a task
    if inner_tool_name in ("update_task", "claim_task"):
        if task_id and session_task_manager:
            try:
                session_task_manager.link_task(state.session_id, task_id, "worked_on")
                logger.info(f"Auto-linked task {task_id} to session {state.session_id}")
            except Exception as e:
                logger.warning(f"Failed to auto-link task {task_id}: {e}")


def detect_plan_mode_from_context(prompt: str, state: "WorkflowState") -> None:
    """Detect plan mode from system reminders injected by Claude Code.

    Claude Code injects system reminders like "Plan mode is active" when the user
    enters plan mode via the UI (not via the EnterPlanMode tool). This function
    detects those reminders and sets mode_level accordingly.

    IMPORTANT: Only matches indicators within <system-reminder> tags to avoid
    false positives from handoff context or user messages that mention plan mode.

    Args:
        prompt: The user prompt text (may contain system reminders)
        state: Current workflow state (modified in place)
    """
    if not prompt:
        return

    # Extract only content within <system-reminder> tags to avoid false positives
    # from handoff context or user messages mentioning plan mode
    system_reminders = re.findall(r"<system-reminder>(.*?)</system-reminder>", prompt, re.DOTALL)
    reminder_text = " ".join(system_reminders)

    # Claude Code injects these phrases in system reminders when plan mode is active
    plan_mode_indicators = [
        "Plan mode is active",
        "Plan mode still active",
        "You are in plan mode",
    ]

    # Check if plan mode is indicated in system reminders only
    for indicator in plan_mode_indicators:
        if indicator in reminder_text:
            if state.variables.get("mode_level") != 0:
                state.variables["mode_level"] = 0
                logger.info(
                    f"Session {state.session_id}: mode_level=0 (plan) "
                    f"(detected from system reminder: '{indicator}')"
                )
            return

    # Detect exit from plan mode (also only in system reminders)
    exit_indicators = [
        "Exited Plan Mode",
        "Plan mode exited",
    ]

    for indicator in exit_indicators:
        if indicator in reminder_text:
            if state.variables.get("mode_level") == 0:
                chat_mode = state.variables.get("chat_mode", "bypass")
                state.variables["mode_level"] = compute_mode_level(chat_mode)
                logger.info(
                    f"Session {state.session_id}: mode_level={state.variables['mode_level']} "
                    f"(detected from system reminder: '{indicator}')"
                )
            return


def detect_mcp_call(event: "HookEvent", state: "WorkflowState") -> None:
    """Track MCP tool calls by server/tool for workflow conditions.

    Sets state.variables["mcp_calls"] = {
        "gobby-memory": ["recall", "remember"],
        "context7": ["get-library-docs"],
        ...
    }

    This enables workflow conditions like:
        when: "mcp_called('gobby-memory', 'recall')"

    Uses normalized fields from adapters:
    - mcp_server: The MCP server name (normalized from both Claude and Gemini formats)
    - mcp_tool: The tool name on the server (normalized from both formats)
    - tool_output: The tool result (normalized from tool_result/tool_response)

    Args:
        event: The AFTER_TOOL hook event
        state: Current workflow state (modified in place)
    """
    if not event.data:
        return

    # Use normalized fields from adapter layer
    # Adapters extract these from CLI-specific formats:
    # - Claude: tool_input.server_name/tool_name → mcp_server/mcp_tool
    # - Gemini: mcp_context.server_name/tool_name → mcp_server/mcp_tool
    server_name = event.data.get("mcp_server", "")
    inner_tool = event.data.get("mcp_tool", "")

    if not server_name or not inner_tool:
        return

    # Use normalized tool_output (adapters normalize tool_result/tool_response)
    tool_output = event.data.get("tool_output") or {}

    _track_mcp_call(state, server_name, inner_tool, tool_output)


def _track_mcp_call(
    state: "WorkflowState",
    server_name: str,
    inner_tool: str,
    tool_output: dict[str, Any] | Any,
) -> bool:
    """Track a successful MCP call in workflow state.

    Tracks both:
    - That the call was made (in mcp_calls for mcp_called() checks)
    - The result value (in mcp_results for mcp_result_is_null() checks)

    Args:
        state: Current workflow state (modified in place)
        server_name: MCP server name (e.g., "gobby-sessions")
        inner_tool: Tool name on the server (e.g., "get_current_session")
        tool_output: Tool output to check for errors

    Returns:
        True if call succeeded (was tracked), False if it failed (error detected)
    """
    # Extract the result, checking for errors
    result = None
    is_error = False
    if isinstance(tool_output, dict):
        if tool_output.get("error") or tool_output.get("status") == "error":
            is_error = True
        else:
            result = tool_output.get("result")
            if isinstance(result, dict) and result.get("error"):
                is_error = True

    if is_error:
        return False  # Signal that this was an error

    # Track the call (for mcp_called() checks)
    mcp_calls = state.variables.setdefault("mcp_calls", {})
    server_calls = mcp_calls.setdefault(server_name, [])
    if inner_tool not in server_calls:
        server_calls.append(inner_tool)

    # Track the result (for mcp_result_is_null() checks)
    mcp_results = state.variables.setdefault("mcp_results", {})
    server_results = mcp_results.setdefault(server_name, {})
    server_results[inner_tool] = result

    logger.debug(
        f"Session {state.session_id}: MCP call tracked {server_name}/{inner_tool} "
        f"(result={'present' if result is not None else 'null'})"
    )
    return True


# =============================================================================
# Observer engine classes
# =============================================================================


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
            raise ValueError(f"Cannot register plugin behavior '{name}': already registered")
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
                    f"Observer '{obs.name}' failed to evaluate set expression for '{var_name}': {e}"
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
    """Behavior: track task claims/releases via detect_task_claim."""
    if event is None:
        return

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
    """Behavior: detect plan mode from system-reminder tags."""
    if event is None or not event.data:
        return

    prompt = event.data.get("prompt", "") or ""
    detect_plan_mode_from_context(prompt, state)


async def _mcp_call_tracking(
    event: "HookEvent | None",
    state: WorkflowState,
    **kwargs: Any,
) -> None:
    """Behavior: track MCP tool calls in state variables."""
    if event is None:
        return

    detect_mcp_call(event, state)


def get_default_registry() -> BehaviorRegistry:
    """Create a BehaviorRegistry with all built-in behaviors registered."""
    registry = BehaviorRegistry()
    registry.register("task_claim_tracking", _task_claim_tracking)
    registry.register("detect_plan_mode", _detect_plan_mode)
    registry.register("mcp_call_tracking", _mcp_call_tracking)
    return registry
