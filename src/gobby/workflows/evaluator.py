import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .definitions import WorkflowState

logger = logging.getLogger(__name__)

# Approval keywords (case-insensitive)
APPROVAL_KEYWORDS = {"yes", "approve", "approved", "proceed", "continue", "ok", "okay", "y"}
REJECTION_KEYWORDS = {"no", "reject", "rejected", "stop", "cancel", "abort", "n"}


@dataclass
class ApprovalCheckResult:
    """Result of checking a user_approval condition."""

    needs_approval: bool = False  # True if we need to request approval
    is_approved: bool = False  # True if user approved
    is_rejected: bool = False  # True if user rejected
    is_timed_out: bool = False  # True if approval timed out
    condition_id: str | None = None  # ID of the condition
    prompt: str | None = None  # Prompt to show user
    timeout_seconds: int | None = None  # Timeout value


def check_approval_response(user_input: str) -> str | None:
    """
    Check if user input contains an approval or rejection keyword.

    Returns:
        "approved" if approval keyword found
        "rejected" if rejection keyword found
        None if no keyword found
    """
    # Normalize input - check if entire input is a keyword or starts with one
    normalized = user_input.strip().lower()

    # Check exact match first
    if normalized in APPROVAL_KEYWORDS:
        return "approved"
    if normalized in REJECTION_KEYWORDS:
        return "rejected"

    # Check if starts with keyword (e.g., "yes, let's proceed")
    # Strip common punctuation from first word
    first_word = normalized.split()[0].rstrip(",.!?:;") if normalized else ""
    if first_word in APPROVAL_KEYWORDS:
        return "approved"
    if first_word in REJECTION_KEYWORDS:
        return "rejected"

    return None


class ConditionEvaluator:
    """
    Evaluates 'when' conditions in workflows.
    Supports simple boolean logic and variable access.
    """

    def __init__(self) -> None:
        """Initialize the condition evaluator."""
        self._plugin_conditions: dict[str, Any] = {}

    def register_plugin_conditions(self, plugin_registry: Any) -> None:
        """
        Register conditions from loaded plugins.

        Conditions are registered with the naming convention:
        plugin_<plugin_name>_<condition_name>

        These can be called in 'when' clauses like:
        when: "plugin_my_plugin_passes_lint()"

        Args:
            plugin_registry: PluginRegistry instance containing loaded plugins.
        """
        if plugin_registry is None:
            return

        for plugin_name, plugin in plugin_registry._plugins.items():
            # Sanitize plugin name for use as identifier
            safe_name = plugin_name.replace("-", "_").replace(".", "_")
            for condition_name, evaluator in plugin._conditions.items():
                full_name = f"plugin_{safe_name}_{condition_name}"
                self._plugin_conditions[full_name] = evaluator
                logger.debug(f"Registered plugin condition: {full_name}")

    def evaluate(self, condition: str, context: dict[str, Any]) -> bool:
        """
        Evaluate a condition string against a context dictionary.

        Args:
            condition: The condition string (e.g., "phase_action_count > 5")
            context: Dictionary containing Available variables (state, event, etc.)

        Returns:
            Boolean result of the evaluation.
        """
        if not condition:
            return True

        try:
            # SAFETY: Using eval() is risky but standard for this type of flexibility until
            # we implement a proper expression parser. We restrict globals to builtins logic.
            # In a production environment, we should use a safer parser like `simpleeval` or `jinja2`.
            # For this MVP, we rely on the context being controlled.

            # Simple sanitization/safety check could go here

            # Allow common helpers
            allowed_globals = {
                "__builtins__": {},
                "len": len,
                "bool": bool,
                "str": str,
                "int": int,
                "list": list,
                "dict": dict,
            }

            # Add plugin conditions as callable functions
            allowed_globals.update(self._plugin_conditions)

            return bool(eval(condition, allowed_globals, context))
        except Exception as e:
            logger.warning(f"Condition evaluation failed: '{condition}'. Error: {e}")
            return False

    def check_exit_conditions(self, conditions: list[dict[str, Any]], state: WorkflowState) -> bool:
        """
        Check if all exit conditions are met. (AND logic)
        """
        context = {
            "workflow_state": state,
            "state": state,  # alias
            # Flatten state for easier access
            "step_action_count": state.step_action_count,
            "total_action_count": state.total_action_count,
            "variables": state.variables,
            "task_list": state.task_list,
        }
        # Add variables safely to avoid shadowing internal context keys
        for key, value in state.variables.items():
            if key in context:
                # Log warning or namespace? For now just skip or simple duplicate warn
                logger.debug(
                    f"Variable '{key}' shadows internal context key, skipping direct merge"
                )
                continue
            context[key] = value

        for condition in conditions:
            cond_type = condition.get("type")

            if cond_type == "variable_set":
                var_name = condition.get("variable")
                if not var_name or var_name not in state.variables:
                    return False

            elif cond_type == "user_approval":
                # User approval condition - check if approval has been granted
                condition_id = condition.get("id", f"approval_{hash(str(condition)) % 10000}")
                approved_var = f"_approval_{condition_id}_granted"

                # Check if this specific approval has been granted
                if not state.variables.get(approved_var, False):
                    return False

            elif cond_type == "expression":
                expr = condition.get("expression")
                if expr and not self.evaluate(expr, context):
                    return False

            # Add other types as needed

        return True

    def check_pending_approval(
        self, conditions: list[dict[str, Any]], state: WorkflowState
    ) -> ApprovalCheckResult | None:
        """
        Check if any user_approval condition needs attention.

        Returns:
            ApprovalCheckResult if there's an approval condition that needs handling,
            None if no approval conditions or all are already granted.
        """
        for condition in conditions:
            if condition.get("type") != "user_approval":
                continue

            condition_id = condition.get("id", f"approval_{hash(str(condition)) % 10000}")
            approved_var = f"_approval_{condition_id}_granted"
            rejected_var = f"_approval_{condition_id}_rejected"

            # Check if already approved
            if state.variables.get(approved_var, False):
                continue

            # Check if rejected
            if state.variables.get(rejected_var, False):
                return ApprovalCheckResult(
                    is_rejected=True,
                    condition_id=condition_id,
                )

            # Check timeout if approval is pending
            timeout = condition.get("timeout")
            if state.approval_pending and state.approval_condition_id == condition_id:
                if timeout and state.approval_requested_at:
                    elapsed = (datetime.now(UTC) - state.approval_requested_at).total_seconds()
                    if elapsed > timeout:
                        return ApprovalCheckResult(
                            is_timed_out=True,
                            condition_id=condition_id,
                            timeout_seconds=timeout,
                        )

            # Need to request approval
            prompt = condition.get("prompt", "Do you approve this action? (yes/no)")
            return ApprovalCheckResult(
                needs_approval=True,
                condition_id=condition_id,
                prompt=prompt,
                timeout_seconds=timeout,
            )

        return None
