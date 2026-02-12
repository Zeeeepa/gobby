from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .definitions import WorkflowState

if TYPE_CHECKING:
    from .webhook_executor import WebhookExecutor

logger = logging.getLogger(__name__)

# Approval keywords (case-insensitive)
APPROVAL_KEYWORDS = {"yes", "approve", "approved", "proceed", "continue", "ok", "okay", "y"}
REJECTION_KEYWORDS = {"no", "reject", "rejected", "stop", "cancel", "abort", "n"}


def is_task_complete(task: Any) -> bool:
    """
    Check if a task counts as complete for workflow purposes.

    A task is complete if:
    - status is 'closed', OR
    - status is 'needs_review' AND requires_user_review is False
      (agent marked for visibility but doesn't need user sign-off)

    Tasks in 'review' with requires_user_review=True are NOT complete
    because they're awaiting user approval.

    Args:
        task: Task object with status and requires_user_review attributes

    Returns:
        True if task is complete, False otherwise
    """
    if task.status == "closed":
        return True
    requires_user_review = getattr(task, "requires_user_review", False)
    if task.status == "needs_review" and not requires_user_review:
        return True
    return False


def task_needs_user_review(task_manager: Any, task_id: str | None) -> bool:
    """
    Check if a task is awaiting user review (in review + HITL flag).

    Used in workflow transition conditions like:
        when: "task_needs_user_review(variables.session_task)"

    Args:
        task_manager: LocalTaskManager instance for querying tasks
        task_id: Task ID to check

    Returns:
        True if task is in 'needs_review' status AND has requires_user_review=True.
        Returns False if task_id is None or task not found.
    """
    if not task_id or not task_manager:
        return False

    task = task_manager.get_task(task_id)
    if not task:
        return False

    return bool(task.status == "needs_review" and getattr(task, "requires_user_review", False))


def task_tree_complete(task_manager: Any, task_id: str | list[str] | None) -> bool:
    """
    Check if a task and all its subtasks are complete.

    A task is complete if:
    - status is 'closed', OR
    - status is 'needs_review' AND requires_user_review is False

    Used in workflow transition conditions like:
        when: "task_tree_complete(variables.session_task)"

    Args:
        task_manager: LocalTaskManager instance for querying tasks
        task_id: Single task ID, list of task IDs, or None

    Returns:
        True if all tasks and their subtasks are complete, False otherwise.
        Returns True if task_id is None (no task to check).
    """
    if not task_id:
        return True

    if not task_manager:
        logger.warning("task_tree_complete: No task_manager available")
        return False

    # Normalize to list
    task_ids = [task_id] if isinstance(task_id, str) else task_id

    for tid in task_ids:
        # Get the task itself
        task = task_manager.get_task(tid)
        if not task:
            logger.warning(f"task_tree_complete: Task '{tid}' not found")
            return False

        # Check if main task is complete
        if not is_task_complete(task):
            logger.debug(f"task_tree_complete: Task '{tid}' is not complete (status={task.status})")
            return False

        # Check all subtasks recursively
        if not _subtasks_complete(task_manager, tid):
            return False

    return True


def _subtasks_complete(task_manager: Any, parent_id: str) -> bool:
    """Recursively check if all subtasks are complete."""
    subtasks = task_manager.list_tasks(parent_task_id=parent_id)

    for subtask in subtasks:
        if not is_task_complete(subtask):
            logger.debug(
                f"_subtasks_complete: Subtask '{subtask.id}' is not complete (status={subtask.status})"
            )
            return False

        # Recursively check subtasks of this subtask
        if not _subtasks_complete(task_manager, subtask.id):
            return False

    return True


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
    Evaluates 'when' conditions in workflows using SafeExpressionEvaluator (AST-based).
    Supports boolean logic, comparisons, function calls, and variable access.
    """

    def __init__(self) -> None:
        """Initialize the condition evaluator."""
        self._plugin_conditions: dict[str, Any] = {}
        self._task_manager: Any = None
        self._stop_registry: Any = None
        self._webhook_executor: WebhookExecutor | None = None

    def register_task_manager(self, task_manager: Any) -> None:
        """
        Register a task manager for task-related condition helpers.

        This enables the task_tree_complete() function in workflow conditions.

        Args:
            task_manager: LocalTaskManager instance
        """
        self._task_manager = task_manager
        logger.debug("ConditionEvaluator: task_manager registered")

    def register_stop_registry(self, stop_registry: Any) -> None:
        """
        Register a stop registry for stop signal condition helpers.

        This enables the has_stop_signal() function in workflow conditions.

        Args:
            stop_registry: StopRegistry instance
        """
        self._stop_registry = stop_registry
        logger.debug("ConditionEvaluator: stop_registry registered")

    def register_webhook_executor(self, webhook_executor: WebhookExecutor | None) -> None:
        """
        Register a webhook executor for webhook condition evaluation.

        This enables webhook conditions in workflow transitions.

        Args:
            webhook_executor: WebhookExecutor instance
        """
        self._webhook_executor = webhook_executor
        logger.debug("ConditionEvaluator: webhook_executor registered")

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

        Uses SafeExpressionEvaluator (AST-based) instead of eval() for security.

        Args:
            condition: The condition string (e.g., "phase_action_count > 5")
            context: Dictionary containing available variables (state, event, etc.)

        Returns:
            Boolean result of the evaluation.
        """
        if not condition:
            return True

        try:
            from .safe_evaluator import SafeExpressionEvaluator, build_condition_helpers

            # Build allowed functions with all helpers
            allowed_funcs = build_condition_helpers(
                task_manager=self._task_manager,
                stop_registry=self._stop_registry,
                plugin_conditions=self._plugin_conditions,
                context=context,
            )

            # Add YAML/JSON lowercase boolean aliases to context
            eval_context = {
                "true": True,
                "false": False,
            }
            eval_context.update(context)

            evaluator = SafeExpressionEvaluator(eval_context, allowed_funcs)
            return evaluator.evaluate(condition)
        except Exception as e:
            logger.warning(f"Condition evaluation failed: '{condition}'. Error: {e}")
            return False

    def check_exit_conditions(
        self,
        conditions: list[dict[str, Any] | str],
        state: WorkflowState,
        exit_when: str | None = None,
    ) -> bool:
        """
        Check if all exit conditions are met. (AND logic)

        Supports:
        - exit_when: expression string AND-ed with conditions
        - String items in conditions: treated as expression shorthand
        - {approval: prompt}: sugar for {type: user_approval, prompt: prompt}
        - {webhook: {url: ...}}: sugar for {type: webhook, url: ...}
        - Old dict format: {type: variable_set/expression/user_approval/webhook, ...}
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
                logger.debug(
                    f"Variable '{key}' shadows internal context key, skipping direct merge"
                )
                continue
            context[key] = value

        # Evaluate exit_when first (AND-ed with conditions)
        if exit_when and not self.evaluate(exit_when, context):
            return False

        for condition in conditions:
            normalized = self._normalize_condition(condition)

            cond_type = normalized.get("type")

            if cond_type == "variable_set":
                var_name = normalized.get("variable")
                if not var_name or var_name not in state.variables:
                    return False

            elif cond_type == "user_approval":
                condition_id = normalized.get(
                    "id", f"approval_{hash(str(normalized)) % 10000}"
                )
                approved_var = f"_approval_{condition_id}_granted"
                if not state.variables.get(approved_var, False):
                    return False

            elif cond_type == "expression":
                expr = normalized.get("expression")
                if expr and not self.evaluate(expr, context):
                    return False

            elif cond_type == "webhook":
                condition_id = normalized.get(
                    "id", f"webhook_{hash(str(normalized)) % 10000}"
                )
                result_var = f"_webhook_{condition_id}_result"
                webhook_result = state.variables.get(result_var)
                if webhook_result is None:
                    logger.warning(
                        f"Webhook condition '{condition_id}' not pre-evaluated. "
                        "Call evaluate_webhook_conditions() first."
                    )
                    return False
                if not self._check_webhook_result(normalized, webhook_result):
                    return False

        return True

    @staticmethod
    def _normalize_condition(condition: dict[str, Any] | str) -> dict[str, Any]:
        """Normalize a condition to canonical dict format.

        Handles:
        - String: expression shorthand
        - {approval: prompt}: user_approval sugar
        - {webhook: {...}}: webhook sugar
        - Dict with 'type': pass through as-is
        """
        if isinstance(condition, str):
            return {"type": "expression", "expression": condition}

        if "approval" in condition:
            result: dict[str, Any] = {
                "type": "user_approval",
                "prompt": condition["approval"],
            }
            if "id" in condition:
                result["id"] = condition["id"]
            return result

        if "webhook" in condition:
            webhook_config = condition["webhook"]
            result = {"type": "webhook"}
            if isinstance(webhook_config, dict):
                result.update(webhook_config)
            if "id" in condition:
                result["id"] = condition["id"]
            return result

        return condition

    def _check_webhook_result(self, condition: dict[str, Any], result: dict[str, Any]) -> bool:
        """Check if webhook result matches the condition criteria.

        Args:
            condition: Webhook condition configuration
            result: Pre-evaluated webhook result stored in state

        Returns:
            True if condition is satisfied
        """
        if not isinstance(result, dict):
            return False

        # Check success (default: require success)
        expect_success = condition.get("expect_success", True)
        if expect_success and not result.get("success", False):
            return False
        if not expect_success and result.get("success", False):
            return False

        # Check status code if specified
        expected_status = condition.get("status_code")
        if expected_status is not None:
            actual_status = result.get("status_code")
            if isinstance(expected_status, list):
                if actual_status not in expected_status:
                    return False
            elif actual_status != expected_status:
                return False

        # Check body contains string if specified
        body_contains = condition.get("body_contains")
        if body_contains:
            body = result.get("body", "")
            if body_contains not in body:
                return False

        # Check JSON body field if specified (dot notation: "data.approved")
        json_field = condition.get("json_field")
        if json_field:
            json_body = result.get("json_body", {})
            expected_value = condition.get("json_value")
            actual_value = self._get_nested_value(json_body, json_field)

            if expected_value is not None:
                if actual_value != expected_value:
                    return False
            else:
                # Just check field exists and is truthy
                if not actual_value:
                    return False

        return True

    def _get_nested_value(self, obj: dict[str, Any], path: str) -> Any:
        """Get a nested value from a dict using dot notation.

        Args:
            obj: Dictionary to traverse
            path: Dot-separated path (e.g., "data.user.name")

        Returns:
            Value at path, or None if not found
        """
        parts = path.split(".")
        current: Any = obj
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None
        return current

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

    async def evaluate_webhook_conditions(
        self, conditions: list[dict[str, Any]], state: WorkflowState
    ) -> dict[str, Any]:
        """
        Pre-evaluate webhook conditions and store results in state variables.

        This async method must be called before check_exit_conditions() for
        workflows that include webhook conditions. Results are stored in
        state.variables with keys like "_webhook_<id>_result".

        Args:
            conditions: List of condition dicts from workflow definition
            state: Current workflow state (will be modified)

        Returns:
            Dict with evaluation summary:
            - evaluated: Number of webhook conditions evaluated
            - results: Dict mapping condition_id to webhook result
            - errors: List of any errors encountered

        Example webhook condition config:
            {
                "type": "webhook",
                "id": "approval_check",
                "url": "https://api.example.com/approve",
                "method": "POST",  # Optional, default POST
                "headers": {"Authorization": "Bearer ${secrets.API_KEY}"},
                "payload": {"session_id": "{{ session_id }}"},
                "timeout": 30,  # Optional, default 30s
                "expect_success": true,  # Check response is 2xx
                "status_code": 200,  # Or [200, 201] for multiple
                "body_contains": "approved",  # Check body contains string
                "json_field": "data.approved",  # Check JSON field
                "json_value": true,  # Expected value (optional)
                "store_as": "approval_response"  # Store full result in variable
            }
        """
        if not self._webhook_executor:
            logger.warning("No webhook_executor registered for condition evaluation")
            return {"evaluated": 0, "results": {}, "errors": ["No webhook executor"]}

        evaluated = 0
        results: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        for condition in conditions:
            if condition.get("type") != "webhook":
                continue

            condition_id = condition.get("id", f"webhook_{hash(str(condition)) % 10000}")

            try:
                # Execute the webhook
                webhook_result = await self._webhook_executor.execute(
                    url=condition.get("url", ""),
                    method=condition.get("method", "POST"),
                    headers=condition.get("headers"),
                    payload=condition.get("payload"),
                    timeout=condition.get("timeout", 30),
                    context={
                        "session_id": state.session_id,
                        "workflow_name": state.workflow_name,
                        "step": state.step,
                        "variables": state.variables,
                    },
                )

                # Convert result to storable dict
                try:
                    json_body = webhook_result.json_body()
                except Exception:
                    json_body = None

                result_dict: dict[str, Any] = {
                    "success": webhook_result.success,
                    "status_code": webhook_result.status_code,
                    "body": webhook_result.body,
                    "error": webhook_result.error,
                    "json_body": json_body,
                }

                # Store result in state variables
                result_var = f"_webhook_{condition_id}_result"
                state.variables[result_var] = result_dict

                # Also store in named variable if specified
                store_as = condition.get("store_as")
                if store_as:
                    state.variables[store_as] = result_dict

                results[condition_id] = result_dict
                evaluated += 1

                logger.debug(
                    f"Webhook condition '{condition_id}' evaluated: "
                    f"status={webhook_result.status_code}, success={webhook_result.success}"
                )

            except Exception as e:
                error_msg = f"Webhook condition '{condition_id}' failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

                # Store error result
                result_var = f"_webhook_{condition_id}_result"
                state.variables[result_var] = {
                    "success": False,
                    "status_code": None,
                    "body": None,
                    "error": str(e),
                    "json_body": None,
                }

        return {
            "evaluated": evaluated,
            "results": results,
            "errors": errors,
        }
