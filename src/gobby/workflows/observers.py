"""Observer engine for YAML observer matching and variable setting.

Evaluates Observer definitions against hook events and updates workflow
state variables when matches occur.
"""

import logging
from typing import Any

from jinja2 import Environment

from gobby.workflows.definitions import Observer, WorkflowState

logger = logging.getLogger(__name__)

# Shared Jinja2 environment for evaluating set expressions
_jinja_env = Environment()


class ObserverEngine:
    """Evaluates YAML observers against events and sets variables."""

    async def evaluate_observers(
        self,
        observers: list[Observer],
        event_type: str,
        event_data: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        """Evaluate all observers against an event, updating state variables.

        Args:
            observers: List of Observer definitions to evaluate
            event_type: The event type string (e.g., "after_tool", "before_tool")
            event_data: Hook event data dict (tool_name, tool_input, etc.)
            state: Workflow state to update on match
        """
        for obs in observers:
            # Skip behavior refs — handled by separate behavior registry
            if obs.behavior is not None:
                continue

            # Check event type matches
            if obs.on != event_type:
                continue

            # Check match criteria (AND logic)
            if not self._matches(obs, event_data):
                continue

            # Apply set expressions
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
    ) -> str:
        """Evaluate a set expression (Jinja2 template or literal).

        Returns the rendered string value.
        """
        # If it contains Jinja2 template markers, render as template
        if "{{" in expression:
            template = _jinja_env.from_string(expression)
            context = {
                "variables": state.variables,
                "event_data": event_data,
            }
            return template.render(**context)

        # Otherwise treat as literal value
        return expression
