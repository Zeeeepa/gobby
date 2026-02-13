"""Unified workflow evaluation loop for multi-workflow per session.

Evaluates events across multiple concurrent workflow instances sorted by
priority. Accumulates context, enforces tool restrictions, evaluates step
transitions, and stops on first block.

This module is the single evaluation entry point for the unified workflow
architecture (replacing the dual lifecycle/step evaluation paths).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.workflows.definitions import WorkflowDefinition, WorkflowInstance, WorkflowStep
from gobby.workflows.safe_evaluator import SafeExpressionEvaluator

# Type alias for pluggable condition evaluator functions.
# Matches ConditionEvaluator.evaluate(condition, context) signature.
ConditionEvaluatorFn = Callable[[str, dict[str, Any]], bool]

logger = logging.getLogger(__name__)

# Read-only MCP discovery tools always allowed regardless of workflow restrictions.
EXEMPT_TOOLS = frozenset(
    {
        "list_mcp_servers",
        "mcp__gobby__list_mcp_servers",
        "list_tools",
        "mcp__gobby__list_tools",
        "get_tool_schema",
        "mcp__gobby__get_tool_schema",
        "recommend_tools",
        "mcp__gobby__recommend_tools",
        "search_tools",
        "mcp__gobby__search_tools",
    }
)

# Maximum auto-transition chain depth to prevent infinite loops.
_MAX_CHAIN_DEPTH = 10


class DotDict(dict[str, Any]):
    """Dict subclass supporting both dot-notation and .get() access."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


@dataclass
class EvaluationResult:
    """Result of evaluating an event across all workflow instances."""

    decision: str = "allow"
    context_parts: list[str] = field(default_factory=list)
    system_messages: list[str] = field(default_factory=list)
    reason: str | None = None
    blocked_by: str | None = None
    transitions: dict[str, str] = field(default_factory=dict)

    def to_hook_response(self) -> HookResponse:
        """Convert to a HookResponse for the hook system."""
        return HookResponse(
            decision=self.decision,  # type: ignore[arg-type]
            context="\n\n".join(self.context_parts) if self.context_parts else None,
            system_message="\n".join(self.system_messages) if self.system_messages else None,
            reason=self.reason,
        )


def evaluate_event(
    event: HookEvent,
    instances: list[WorkflowInstance],
    definitions: dict[str, WorkflowDefinition],
    session_variables: dict[str, Any] | None = None,
    condition_evaluator: ConditionEvaluatorFn | None = None,
) -> EvaluationResult:
    """Evaluate an event across all active workflow instances.

    Processes instances in priority order (caller must pre-sort). For each:
    1. Skip disabled instances or those with no matching definition.
    2. Build evaluation context with workflow + session variable namespaces.
    3. For BEFORE_TOOL events: evaluate step tool restrictions.
    4. Evaluate step transitions (with auto-chain follow-through).
    5. Evaluate workflow triggers for context injection.
    6. Accumulate context; stop immediately on first block.

    Args:
        event: The hook event to evaluate.
        instances: Workflow instances, pre-sorted by priority (ascending).
        definitions: Map of workflow_name -> WorkflowDefinition.
        session_variables: Shared session-scoped variables.

    Returns:
        EvaluationResult with accumulated context and decision.
    """
    result = EvaluationResult()
    session_vars = session_variables or {}

    for instance in instances:
        if not instance.enabled:
            continue

        definition = definitions.get(instance.workflow_name)
        if not definition:
            continue

        eval_ctx = _build_eval_context(event, instance, definition, session_vars)

        # For BEFORE_TOOL events: check tool restrictions
        if event.event_type == HookEventType.BEFORE_TOOL:
            tool_name = event.data.get("tool_name", "")
            step = definition.get_step(instance.current_step) if instance.current_step else None
            if step:
                decision, reason = _evaluate_step_tool_rules(
                    tool_name, step, eval_ctx, condition_evaluator
                )
                if decision == "block":
                    result.decision = "block"
                    result.reason = reason
                    result.blocked_by = instance.workflow_name
                    return result

        # Evaluate step transitions
        if instance.current_step:
            step = definition.get_step(instance.current_step)
            if step:
                new_step = _evaluate_step_transitions(step, eval_ctx, condition_evaluator)
                if new_step:
                    # Follow auto-transition chain
                    visited = {instance.current_step, new_step}
                    depth = 0
                    while new_step and depth < _MAX_CHAIN_DEPTH:
                        next_step_def = definition.get_step(new_step)
                        if not next_step_def:
                            break
                        chain_target = _evaluate_step_transitions(
                            next_step_def, eval_ctx, condition_evaluator
                        )
                        if chain_target and chain_target not in visited:
                            visited.add(chain_target)
                            new_step = chain_target
                            depth += 1
                        else:
                            break
                    result.transitions[instance.workflow_name] = new_step

                    # Add status message from target step
                    target_step = definition.get_step(new_step)
                    if target_step and target_step.status_message:
                        result.context_parts.append(target_step.status_message)

        # Evaluate workflow triggers for context injection
        trigger_context = _evaluate_triggers(event, definition, eval_ctx, condition_evaluator)
        result.context_parts.extend(trigger_context)

    return result


def _evaluate_step_tool_rules(
    tool_name: str,
    step: WorkflowStep,
    eval_context: dict[str, Any],
    condition_evaluator: ConditionEvaluatorFn | None = None,
) -> tuple[str, str | None]:
    """Evaluate step-level tool restrictions.

    Checks in order:
    1. Exempt tools (MCP discovery) — always allowed.
    2. Explicit blocked_tools list.
    3. allowed_tools whitelist (unless "all").
    4. Named rules with conditions.

    Args:
        tool_name: Name of the tool being checked.
        step: The current workflow step definition.
        eval_context: Variables available for condition evaluation.
        condition_evaluator: Optional pluggable evaluator matching
            ConditionEvaluator.evaluate(condition, context) signature.
            Falls back to SafeExpressionEvaluator when None.

    Returns:
        Tuple of (decision, reason). Decision is "allow" or "block".
    """
    if tool_name in EXEMPT_TOOLS:
        return "allow", None

    if tool_name in step.blocked_tools:
        return "block", f"Tool '{tool_name}' is blocked in step '{step.name}'."

    if step.allowed_tools != "all" and tool_name not in step.allowed_tools:
        return "block", f"Tool '{tool_name}' is not in allowed list for step '{step.name}'."

    for rule in step.rules:
        if rule.when and rule.action == "block":
            try:
                if condition_evaluator:
                    matched = condition_evaluator(rule.when, eval_context)
                else:
                    evaluator = SafeExpressionEvaluator(eval_context, {})
                    matched = evaluator.evaluate(rule.when)
                if matched:
                    return "block", rule.message or f"Blocked by rule in step '{step.name}'"
            except (ValueError, Exception):
                logger.debug("Failed to evaluate rule condition: %s", rule.when, exc_info=True)

    return "allow", None


def _evaluate_step_transitions(
    step: WorkflowStep,
    eval_context: dict[str, Any],
    condition_evaluator: ConditionEvaluatorFn | None = None,
) -> str | None:
    """Evaluate step transitions and return target step name if any fires.

    Transitions are evaluated in order; first match wins.

    Args:
        step: The current workflow step definition.
        eval_context: Variables available for condition evaluation.
        condition_evaluator: Optional pluggable evaluator matching
            ConditionEvaluator.evaluate(condition, context) signature.
            Falls back to SafeExpressionEvaluator when None.

    Returns:
        Name of the target step, or None if no transition fires.
    """
    for transition in step.transitions:
        try:
            if condition_evaluator:
                matched = condition_evaluator(transition.when, eval_context)
            else:
                evaluator = SafeExpressionEvaluator(eval_context, {})
                matched = evaluator.evaluate(transition.when)
            if matched:
                return transition.to
        except (ValueError, Exception):
            logger.debug(
                "Failed to evaluate transition condition: %s", transition.when, exc_info=True
            )
    return None


# Map HookEventType to trigger key names in WorkflowDefinition.triggers.
_TRIGGER_KEY_MAP: dict[HookEventType, str] = {
    HookEventType.SESSION_START: "on_session_start",
    HookEventType.SESSION_END: "on_session_end",
    HookEventType.BEFORE_TOOL: "on_before_tool",
    HookEventType.AFTER_TOOL: "on_after_tool",
    HookEventType.BEFORE_AGENT: "on_before_agent",
    HookEventType.AFTER_AGENT: "on_after_agent",
    HookEventType.STOP: "on_stop",
    HookEventType.PRE_COMPACT: "on_pre_compact",
}


def _evaluate_triggers(
    event: HookEvent,
    definition: WorkflowDefinition,
    eval_context: dict[str, Any],
    condition_evaluator: ConditionEvaluatorFn | None = None,
) -> list[str]:
    """Evaluate workflow-level triggers for the given event.

    Currently processes inject_context actions only. Other action types
    (set_variable, block_tools, etc.) require the full action engine.

    Args:
        event: The hook event being evaluated.
        definition: Workflow definition containing triggers.
        eval_context: Variables available for condition evaluation.
        condition_evaluator: Optional pluggable evaluator matching
            ConditionEvaluator.evaluate(condition, context) signature.
            Falls back to SafeExpressionEvaluator when None.

    Returns:
        List of context messages from matching triggers.
    """
    context_parts: list[str] = []

    trigger_key = _TRIGGER_KEY_MAP.get(event.event_type)
    if not trigger_key or trigger_key not in definition.triggers:
        return context_parts

    for action in definition.triggers[trigger_key]:
        if action.get("action") != "inject_context":
            continue

        when = action.get("when")
        if when:
            try:
                if condition_evaluator:
                    matched = condition_evaluator(when, eval_context)
                else:
                    evaluator = SafeExpressionEvaluator(eval_context, {})
                    matched = evaluator.evaluate(when)
                if not matched:
                    continue
            except (ValueError, Exception):
                logger.debug("Failed to evaluate trigger condition: %s", when, exc_info=True)
                continue

        content = action.get("content", "")
        if content:
            context_parts.append(content)

    return context_parts


def _build_eval_context(
    event: HookEvent,
    instance: WorkflowInstance,
    definition: WorkflowDefinition,
    session_variables: dict[str, Any],
) -> dict[str, Any]:
    """Build evaluation context with both workflow-scoped and session-scoped variables.

    Provides:
    - variables.* — workflow-scoped variables (definition defaults + instance overrides)
    - session.* — session-scoped shared variables
    - step, step_action_count, total_action_count — instance step state
    - tool_name, tool_args — from event data
    - Flattened workflow variables at top level for convenience
    """
    workflow_vars = {**definition.variables, **instance.variables}

    ctx: dict[str, Any] = {
        "variables": DotDict(workflow_vars),
        "session": DotDict(session_variables),
        "step": instance.current_step,
        "step_action_count": instance.step_action_count,
        "total_action_count": instance.total_action_count,
        "tool_name": event.data.get("tool_name"),
        "tool_args": event.data.get("tool_args", {}),
        "event_type": event.event_type.value,
        "workflow_name": instance.workflow_name,
    }

    # Flatten workflow variables to top level
    ctx.update(workflow_vars)

    return ctx
