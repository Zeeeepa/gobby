"""Rule engine with single-pass evaluation loop.

Rules are stateless event handlers: event comes in, conditions match, effect fires.
Four effect types: block, set_variable, inject_context, mcp_call.
"""

import json
import logging
import re
from typing import Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.storage.config_store import ConfigStore
from gobby.storage.database import DatabaseProtocol
from gobby.storage.workflow_definitions import (
    LocalWorkflowDefinitionManager,
    WorkflowDefinitionRow,
)
from gobby.workflows.definitions import RuleDefinitionBody, RuleEvent
from gobby.workflows.enforcement.blocking import (
    is_discovery_tool,
    is_server_listed,
    is_tool_unlocked,
)
from gobby.workflows.safe_evaluator import SafeExpressionEvaluator, build_condition_helpers
from gobby.workflows.templates import TemplateEngine

logger = logging.getLogger(__name__)

# Map HookEventType to RuleEvent
_EVENT_TYPE_MAP: dict[HookEventType, RuleEvent] = {
    HookEventType.BEFORE_TOOL: RuleEvent.BEFORE_TOOL,
    HookEventType.AFTER_TOOL: RuleEvent.AFTER_TOOL,
    HookEventType.BEFORE_AGENT: RuleEvent.BEFORE_AGENT,
    HookEventType.SESSION_START: RuleEvent.SESSION_START,
    HookEventType.SESSION_END: RuleEvent.SESSION_END,
    HookEventType.STOP: RuleEvent.STOP,
    HookEventType.PRE_COMPACT: RuleEvent.PRE_COMPACT,
}


class RuleEngine:
    """Single-pass rule evaluation engine.

    Loads rules from workflow_definitions (workflow_type='rule'),
    applies session overrides, evaluates in priority order.
    """

    def __init__(self, db: DatabaseProtocol):
        self.db = db
        self.definition_manager = LocalWorkflowDefinitionManager(db)

    async def evaluate(
        self,
        event: HookEvent,
        session_id: str,
        variables: dict[str, Any],
        eval_context: dict[str, Any] | None = None,
    ) -> HookResponse:
        """Evaluate all matching rules for an event.

        Args:
            event: The hook event to evaluate.
            session_id: Current session ID (for overrides).
            variables: Session variables dict (mutated in-place by set_variable).
            eval_context: Additional eval context (LazyBool thunks, etc).

        Returns:
            HookResponse with merged results from all matching rules.
        """
        rule_event = _EVENT_TYPE_MAP.get(event.event_type)
        if rule_event is None:
            return HookResponse(decision="allow")

        # Check global enforcement toggle
        config_store = ConfigStore(self.db)
        if config_store.get("rules.enforcement_enabled") is False:
            return HookResponse(decision="allow")

        # 1. Load enabled rules for this event, sorted by priority
        rules = self._load_rules(rule_event)

        # 2. Apply session overrides
        overrides = self._load_session_overrides(session_id)
        rules = self._apply_overrides(rules, overrides)

        # 3. Filter by agent_scope
        agent_type = variables.get("_agent_type")
        rules = self._filter_by_agent_scope(rules, agent_type)

        if not rules:
            return HookResponse(decision="allow")

        # 4. Evaluate rules in priority order
        context_parts: list[str] = []
        mcp_calls: list[dict[str, Any]] = []
        block_reason: str | None = None

        for _row, body in rules:
            # Build fresh eval context with current variables
            ctx = self._build_eval_context(event, variables, eval_context)
            effect = body.effect

            # Check `when` condition
            if body.when:
                if not self._evaluate_condition(body.when, ctx, effect.type):
                    continue

            # Apply effect
            if effect.type == "block":
                if self._should_block(effect, event):
                    block_reason = effect.reason or "Blocked by rule"
                    # Render Jinja templates in reason (e.g. {{ tool_input.get('server_name') }})
                    if block_reason and "{{" in block_reason:
                        try:
                            engine = TemplateEngine()
                            block_reason = engine.render(block_reason, ctx)
                        except Exception as e:
                            logger.warning(f"Failed to render block reason template: {e}")
                    block_reason = f"Rule enforced by Gobby: [{_row.name}]\n{block_reason}"
                    # First block wins — stop evaluating
                    break

            elif effect.type == "set_variable":
                self._apply_set_variable(effect, variables, ctx)

            elif effect.type == "inject_context":
                if effect.template:
                    template_text = effect.template
                    if "{{" in template_text:
                        try:
                            engine = TemplateEngine()
                            template_text = engine.render(template_text, ctx)
                        except Exception as e:
                            logger.warning(f"Failed to render inject_context template: {e}")
                    context_parts.append(template_text)

            elif effect.type == "mcp_call":
                mcp_calls.append(
                    {
                        "server": effect.server,
                        "tool": effect.tool,
                        "arguments": effect.arguments or {},
                        "background": effect.background,
                    }
                )

        # 5. Build response
        if block_reason:
            return HookResponse(
                decision="block",
                reason=block_reason,
                context="\n\n".join(context_parts) if context_parts else None,
                metadata={"mcp_calls": mcp_calls} if mcp_calls else {},
            )

        return HookResponse(
            decision="allow",
            context="\n\n".join(context_parts) if context_parts else None,
            metadata={"mcp_calls": mcp_calls} if mcp_calls else {},
        )

    def _load_rules(
        self, rule_event: RuleEvent
    ) -> list[tuple[WorkflowDefinitionRow, RuleDefinitionBody]]:
        """Load enabled rules matching the event type, sorted by priority."""
        rows = self.definition_manager.list_rules_by_event(
            event=rule_event.value,
            enabled=True,
        )
        result: list[tuple[WorkflowDefinitionRow, RuleDefinitionBody]] = []
        for row in rows:
            try:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                result.append((row, body))
            except Exception as e:
                logger.warning(f"Failed to parse rule {row.name}: {e}")
        return result

    def _load_session_overrides(self, session_id: str) -> dict[str, bool]:
        """Load session-scoped rule overrides."""
        rows = self.db.fetchall(
            "SELECT rule_name, enabled FROM rule_overrides WHERE session_id = ?",
            (session_id,),
        )
        return {row["rule_name"]: bool(row["enabled"]) for row in rows}

    def _apply_overrides(
        self,
        rules: list[tuple[WorkflowDefinitionRow, RuleDefinitionBody]],
        overrides: dict[str, bool],
    ) -> list[tuple[WorkflowDefinitionRow, RuleDefinitionBody]]:
        """Filter rules based on session overrides."""
        if not overrides:
            return rules
        return [
            (row, body)
            for row, body in rules
            if overrides.get(row.name, True)  # Default to enabled if no override
        ]

    def _filter_by_agent_scope(
        self,
        rules: list[tuple[WorkflowDefinitionRow, RuleDefinitionBody]],
        agent_type: str | None,
    ) -> list[tuple[WorkflowDefinitionRow, RuleDefinitionBody]]:
        """Filter rules by agent_scope.

        - Rules with no agent_scope (None) are global — always included.
        - Rules with agent_scope require _agent_type to be in the list.
        - If no _agent_type is set, only global rules are included.
        """
        return [
            (row, body)
            for row, body in rules
            if body.agent_scope is None
            or (agent_type is not None and agent_type in body.agent_scope)
        ]

    def _build_eval_context(
        self,
        event: HookEvent,
        variables: dict[str, Any],
        extra_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build evaluation context for condition checking."""
        raw_tool_input = event.data.get("tool_input") or event.data.get("arguments") or {}

        # For MCP call_tool, unwrap nested arguments so rule conditions
        # can reference inner tool params (commit_sha, reason, etc.) directly.
        tool_name = event.data.get("tool_name", "")
        if tool_name in ("call_tool", "mcp__gobby__call_tool") and isinstance(raw_tool_input, dict):
            inner_args = raw_tool_input.get("arguments")
            if isinstance(inner_args, str):
                try:
                    parsed = json.loads(inner_args)
                    if isinstance(parsed, dict):
                        raw_tool_input = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(inner_args, dict):
                raw_tool_input = inner_args

        ctx: dict[str, Any] = {
            "variables": variables,
            "event": event,
            "tool_input": raw_tool_input,
            "source": event.source.value if event.source else None,
        }

        # Flatten variables at top level for convenience
        for key, val in variables.items():
            if key not in ctx:
                ctx[key] = val

        # Add extra context (LazyBool thunks, etc.)
        if extra_context:
            ctx.update(extra_context)

        return ctx

    def _evaluate_condition(
        self, condition: str, context: dict[str, Any], effect_type: str = "block"
    ) -> bool:
        """Evaluate a `when` condition string using SafeExpressionEvaluator.

        On evaluation failure:
        - block effects fail closed (True) — conservative, prevents action
        - other effects fail open (False) — avoids corrupting state or firing unwanted calls
        """
        variables = context.get("variables", {})
        try:
            allowed_funcs = build_condition_helpers(context=context)
            # Rule-engine-specific: progressive disclosure + isinstance
            allowed_funcs["isinstance"] = isinstance
            allowed_funcs["is_server_listed"] = lambda ti: is_server_listed(ti, variables)
            allowed_funcs["is_tool_unlocked"] = lambda ti: is_tool_unlocked(ti, variables)
            allowed_funcs["is_discovery_tool"] = is_discovery_tool

            evaluator = SafeExpressionEvaluator(
                context=context,
                allowed_funcs=allowed_funcs,
            )
            return evaluator.evaluate(condition)
        except Exception as e:
            fail_closed = effect_type == "block"
            logger.error(
                f"Failed to evaluate condition '{condition}': {e} "
                f"(defaulting to {'True' if fail_closed else 'False'} for {effect_type} effect)"
            )
            return fail_closed

    def _should_block(self, effect: Any, event: HookEvent) -> bool:
        """Check if a block effect matches the current tool/event."""
        tool_name = event.data.get("tool_name")
        mcp_tool = event.data.get("mcp_tool")
        mcp_server = event.data.get("mcp_server") or event.data.get("server_name")
        command = event.data.get("command")

        # If no tools/mcp_tools filter specified, block applies to everything
        has_tool_filter = effect.tools or effect.mcp_tools

        if not has_tool_filter:
            # Check command patterns even without tool filter
            if effect.command_pattern and command:
                if not re.search(effect.command_pattern, command):
                    return False
                if effect.command_not_pattern and re.search(effect.command_not_pattern, command):
                    return False
                return True
            return True

        # Check native tool match
        if effect.tools and tool_name:
            if tool_name in effect.tools:
                # Check command patterns for Bash tool
                if tool_name == "Bash" and effect.command_pattern and command:
                    if not re.search(effect.command_pattern, command):
                        return False
                    if effect.command_not_pattern and re.search(
                        effect.command_not_pattern, command
                    ):
                        return False
                return True

        # Check MCP tool match
        if effect.mcp_tools and mcp_tool:
            mcp_key = f"{mcp_server}:{mcp_tool}" if mcp_server else mcp_tool
            for pattern in effect.mcp_tools:
                if pattern == mcp_key:
                    return True
                # Support wildcard: "server:*"
                if pattern.endswith(":*") and mcp_server:
                    server_prefix = pattern[:-2]
                    if server_prefix == mcp_server:
                        return True

        return False

    def _apply_set_variable(
        self,
        effect: Any,
        variables: dict[str, Any],
        eval_context: dict[str, Any],
    ) -> None:
        """Apply a set_variable effect, handling expressions."""
        if effect.variable is None:
            return

        value = effect.value

        # If value is a string that looks like an expression, evaluate it
        if isinstance(value, str) and self._is_expression(value):
            try:
                evaluator = SafeExpressionEvaluator(
                    context=eval_context,
                    allowed_funcs={
                        "len": len,
                        "str": str,
                        "int": int,
                        "bool": bool,
                    },
                )
                value = evaluator.evaluate_value(value)
            except Exception as e:
                logger.warning(f"Failed to evaluate set_variable expression '{effect.value}': {e}")
                return

        variables[effect.variable] = value

    def _is_expression(self, value: str) -> bool:
        """Heuristic: is this string an expression rather than a literal?"""
        expression_indicators = (
            "variables.",
            "event.",
            "tool_input.",
            " + ",
            " - ",
            " and ",
            " or ",
            " not ",
            ".get(",
            "len(",
        )
        return any(indicator in value for indicator in expression_indicators)
