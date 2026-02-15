"""Tests for unified_evaluator.py — single evaluation loop for multi-workflow."""

from datetime import UTC, datetime

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    WorkflowTransition,
)

pytestmark = pytest.mark.unit


def _make_event(
    event_type: HookEventType = HookEventType.BEFORE_TOOL,
    tool_name: str = "Read",
    **kwargs: object,
) -> HookEvent:
    """Create a minimal HookEvent for testing."""
    data: dict = {
        "tool_name": tool_name,
        **(kwargs.get("data", {}) if isinstance(kwargs.get("data"), dict) else {}),
    }  # type: ignore[assignment]
    return HookEvent(
        event_type=event_type,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data,
    )


def _make_instance(
    workflow_name: str = "test-wf",
    *,
    enabled: bool = True,
    priority: int = 100,
    current_step: str | None = None,
    variables: dict | None = None,
) -> WorkflowInstance:
    """Create a minimal WorkflowInstance for testing."""
    return WorkflowInstance(
        id=f"inst-{workflow_name}",
        session_id="test-session",
        workflow_name=workflow_name,
        enabled=enabled,
        priority=priority,
        current_step=current_step,
        variables=variables or {},
    )


def _make_definition(
    name: str = "test-wf",
    steps: list[WorkflowStep] | None = None,
    triggers: dict | None = None,
    variables: dict | None = None,
) -> WorkflowDefinition:
    """Create a minimal WorkflowDefinition for testing."""
    return WorkflowDefinition(
        name=name,
        steps=steps or [],
        triggers=triggers or {},
        variables=variables or {},
    )


class TestEvaluateEvent:
    """Tests for the top-level evaluate_event() function."""

    def test_disabled_workflows_skipped(self) -> None:
        """Disabled workflow instances are skipped entirely."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(tool_name="Write")
        instances = [
            _make_instance("wf-disabled", enabled=False, current_step="work"),
        ]
        definitions = {
            "wf-disabled": _make_definition(
                "wf-disabled",
                steps=[WorkflowStep(name="work", blocked_tools=["Write"])],
            ),
        }

        result = evaluate_event(event, instances, definitions)

        # Disabled workflow's block should not apply
        assert result.decision == "allow"

    def test_evaluates_in_priority_order(self) -> None:
        """Workflows are processed in order (instances pre-sorted by priority)."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(event_type=HookEventType.AFTER_TOOL, tool_name="Read")

        instances = [
            _make_instance("high-pri", priority=10, current_step="work"),
            _make_instance("low-pri", priority=100, current_step="work"),
        ]
        definitions = {
            "high-pri": _make_definition(
                "high-pri",
                steps=[
                    WorkflowStep(
                        name="work",
                        status_message="high-pri context",
                        transitions=[WorkflowTransition(to="done", when="True")],
                    )
                ],
            ),
            "low-pri": _make_definition(
                "low-pri",
                steps=[
                    WorkflowStep(
                        name="work",
                        status_message="low-pri context",
                        transitions=[WorkflowTransition(to="done", when="True")],
                    )
                ],
            ),
        }

        result = evaluate_event(event, instances, definitions)

        # Both workflows should have transitions
        assert "high-pri" in result.transitions
        assert "low-pri" in result.transitions

    def test_context_accumulates_across_workflows(self) -> None:
        """Context from multiple workflows is accumulated."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(event_type=HookEventType.SESSION_START, tool_name="")

        instances = [
            _make_instance("wf-a", priority=10),
            _make_instance("wf-b", priority=20),
        ]
        definitions = {
            "wf-a": _make_definition(
                "wf-a",
                triggers={
                    "on_session_start": [
                        {"action": "inject_context", "content": "Context from A"},
                    ]
                },
            ),
            "wf-b": _make_definition(
                "wf-b",
                triggers={
                    "on_session_start": [
                        {"action": "inject_context", "content": "Context from B"},
                    ]
                },
            ),
        }

        result = evaluate_event(event, instances, definitions)

        assert "Context from A" in result.context_parts
        assert "Context from B" in result.context_parts

    def test_first_block_stops_evaluation(self) -> None:
        """First block decision stops processing remaining workflows."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(tool_name="Write")

        instances = [
            _make_instance("blocker", priority=10, current_step="restricted"),
            _make_instance("permissive", priority=20, current_step="open"),
        ]
        definitions = {
            "blocker": _make_definition(
                "blocker",
                steps=[WorkflowStep(name="restricted", blocked_tools=["Write"])],
            ),
            "permissive": _make_definition(
                "permissive",
                steps=[WorkflowStep(name="open", allowed_tools="all")],
            ),
        }

        result = evaluate_event(event, instances, definitions)

        assert result.decision == "block"
        assert result.blocked_by == "blocker"
        # Permissive workflow should not have been evaluated for transitions
        assert "permissive" not in result.transitions

    def test_missing_definition_skipped(self) -> None:
        """Instances with no matching definition are skipped."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(tool_name="Read")
        instances = [_make_instance("unknown-wf", current_step="work")]
        definitions: dict[str, WorkflowDefinition] = {}  # No definitions

        result = evaluate_event(event, instances, definitions)
        assert result.decision == "allow"


class TestStepToolRules:
    """Tests for _evaluate_step_tool_rules() helper."""

    def test_blocked_tools_enforced(self) -> None:
        """Tools in blocked_tools list are blocked."""
        from gobby.workflows.unified_evaluator import _evaluate_step_tool_rules

        step = WorkflowStep(name="work", blocked_tools=["Write", "Edit"])

        decision, reason = _evaluate_step_tool_rules("Write", step, {})
        assert decision == "block"
        assert "Write" in (reason or "")

    def test_allowed_tools_whitelist(self) -> None:
        """Tools not in allowed_tools list are blocked when not 'all'."""
        from gobby.workflows.unified_evaluator import _evaluate_step_tool_rules

        step = WorkflowStep(name="work", allowed_tools=["Read", "Glob"])

        # Allowed tool
        decision, _ = _evaluate_step_tool_rules("Read", step, {})
        assert decision == "allow"

        # Not in whitelist
        decision, reason = _evaluate_step_tool_rules("Write", step, {})
        assert decision == "block"
        assert "not in allowed" in (reason or "")

    def test_allowed_tools_all(self) -> None:
        """When allowed_tools is 'all', any non-blocked tool is allowed."""
        from gobby.workflows.unified_evaluator import _evaluate_step_tool_rules

        step = WorkflowStep(name="work", allowed_tools="all")

        decision, _ = _evaluate_step_tool_rules("AnyTool", step, {})
        assert decision == "allow"

    def test_exempt_tools_always_allowed(self) -> None:
        """MCP discovery tools are always allowed regardless of restrictions."""
        from gobby.workflows.unified_evaluator import _evaluate_step_tool_rules

        step = WorkflowStep(
            name="locked", allowed_tools=["Read"], blocked_tools=["list_mcp_servers"]
        )

        decision, _ = _evaluate_step_tool_rules("mcp__gobby__list_mcp_servers", step, {})
        assert decision == "allow"

        decision, _ = _evaluate_step_tool_rules("list_tools", step, {})
        assert decision == "allow"


class TestStepTransitions:
    """Tests for _evaluate_step_transitions() helper."""

    def test_transition_fires_when_condition_met(self) -> None:
        """Transition fires when its 'when' condition evaluates to True."""
        from gobby.workflows.unified_evaluator import _evaluate_step_transitions

        step = WorkflowStep(
            name="work",
            transitions=[WorkflowTransition(to="done", when="step_action_count > 5")],
        )
        eval_ctx = {"step_action_count": 10}

        result = _evaluate_step_transitions(step, eval_ctx)
        assert result == "done"

    def test_transition_skipped_when_condition_not_met(self) -> None:
        """Transition does not fire when condition is False."""
        from gobby.workflows.unified_evaluator import _evaluate_step_transitions

        step = WorkflowStep(
            name="work",
            transitions=[WorkflowTransition(to="done", when="step_action_count > 5")],
        )
        eval_ctx = {"step_action_count": 2}

        result = _evaluate_step_transitions(step, eval_ctx)
        assert result is None

    def test_first_matching_transition_wins(self) -> None:
        """Only the first matching transition fires."""
        from gobby.workflows.unified_evaluator import _evaluate_step_transitions

        step = WorkflowStep(
            name="work",
            transitions=[
                WorkflowTransition(to="step_a", when="True"),
                WorkflowTransition(to="step_b", when="True"),
            ],
        )

        result = _evaluate_step_transitions(step, {})
        assert result == "step_a"

    def test_auto_transition_chains(self) -> None:
        """Auto-transition chains follow through multiple steps."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(event_type=HookEventType.AFTER_TOOL)

        instances = [_make_instance("chain-wf", current_step="step_a")]
        definitions = {
            "chain-wf": _make_definition(
                "chain-wf",
                steps=[
                    WorkflowStep(
                        name="step_a",
                        transitions=[WorkflowTransition(to="step_b", when="True")],
                    ),
                    WorkflowStep(
                        name="step_b",
                        transitions=[WorkflowTransition(to="step_c", when="True")],
                    ),
                    WorkflowStep(name="step_c"),  # Terminal step
                ],
            ),
        }

        result = evaluate_event(event, instances, definitions)

        # Should chain through step_a -> step_b -> step_c
        assert result.transitions["chain-wf"] == "step_c"


class TestVariableNamespaces:
    """Tests for variable scoping in evaluation context."""

    def test_session_variables_in_conditions(self) -> None:
        """session.* namespace evaluates against session variables."""
        from gobby.workflows.unified_evaluator import _build_eval_context

        event = _make_event()
        instance = _make_instance("wf", current_step="work")
        definition = _make_definition("wf")
        session_vars = {"task_claimed": True, "stop_attempts": 3}

        ctx = _build_eval_context(event, instance, definition, session_vars)

        assert ctx["session"]["task_claimed"] is True
        assert ctx["session"]["stop_attempts"] == 3

    def test_workflow_variables_in_conditions(self) -> None:
        """variables.* namespace evaluates against workflow-scoped variables."""
        from gobby.workflows.unified_evaluator import _build_eval_context

        event = _make_event()
        instance = _make_instance("wf", current_step="work", variables={"phase": "red"})
        definition = _make_definition("wf", variables={"default_var": "init"})

        ctx = _build_eval_context(event, instance, definition, {})

        # Instance variables override definition defaults
        assert ctx["variables"]["phase"] == "red"
        # Definition defaults available
        assert ctx["variables"]["default_var"] == "init"

    def test_session_condition_evaluation(self) -> None:
        """Transition condition using session.* works end-to-end."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(event_type=HookEventType.AFTER_TOOL)

        instances = [_make_instance("wf", current_step="waiting")]
        definitions = {
            "wf": _make_definition(
                "wf",
                steps=[
                    WorkflowStep(
                        name="waiting",
                        transitions=[
                            WorkflowTransition(to="active", when="session.task_claimed"),
                        ],
                    )
                ],
            ),
        }
        session_vars = {"task_claimed": True}

        result = evaluate_event(event, instances, definitions, session_vars)

        assert result.transitions.get("wf") == "active"

    def test_variables_condition_evaluation(self) -> None:
        """Transition condition using variables.* works end-to-end."""
        from gobby.workflows.unified_evaluator import evaluate_event

        event = _make_event(event_type=HookEventType.AFTER_TOOL)

        instances = [
            _make_instance("wf", current_step="work", variables={"tests_passing": True}),
        ]
        definitions = {
            "wf": _make_definition(
                "wf",
                steps=[
                    WorkflowStep(
                        name="work",
                        transitions=[
                            WorkflowTransition(to="review", when="variables.tests_passing"),
                        ],
                    )
                ],
            ),
        }

        result = evaluate_event(event, instances, definitions)

        assert result.transitions.get("wf") == "review"

    def test_flattened_variables_accessible(self) -> None:
        """Workflow variables are also flattened to top level of eval context."""
        from gobby.workflows.unified_evaluator import _build_eval_context

        event = _make_event()
        instance = _make_instance("wf", variables={"task_claimed": True})
        definition = _make_definition("wf")

        ctx = _build_eval_context(event, instance, definition, {})

        # Available both as variables.task_claimed and task_claimed
        assert ctx["variables"]["task_claimed"] is True
        assert ctx["task_claimed"] is True


class TestEvaluateTriggers:
    """Tests for _evaluate_triggers() helper."""

    def test_matching_trigger_returns_context(self) -> None:
        """Triggers matching the event type produce context."""
        from gobby.workflows.unified_evaluator import _evaluate_triggers

        event = _make_event(event_type=HookEventType.SESSION_START)
        definition = _make_definition(
            triggers={
                "on_session_start": [
                    {"action": "inject_context", "content": "Welcome!"},
                ]
            },
        )

        result = _evaluate_triggers(event, definition, {})
        assert "Welcome!" in result

    def test_non_matching_trigger_skipped(self) -> None:
        """Triggers for different event types are ignored."""
        from gobby.workflows.unified_evaluator import _evaluate_triggers

        event = _make_event(event_type=HookEventType.BEFORE_TOOL)
        definition = _make_definition(
            triggers={
                "on_session_start": [
                    {"action": "inject_context", "content": "Should not appear"},
                ]
            },
        )

        result = _evaluate_triggers(event, definition, {})
        assert len(result) == 0

    def test_conditional_trigger(self) -> None:
        """Triggers with 'when' conditions are evaluated."""
        from gobby.workflows.unified_evaluator import _evaluate_triggers

        event = _make_event(event_type=HookEventType.SESSION_START)
        definition = _make_definition(
            triggers={
                "on_session_start": [
                    {"action": "inject_context", "content": "show", "when": "True"},
                    {"action": "inject_context", "content": "hide", "when": "False"},
                ]
            },
        )

        result = _evaluate_triggers(event, definition, {})
        assert "show" in result
        assert "hide" not in result

    def test_non_inject_actions_ignored(self) -> None:
        """Only inject_context actions produce context in the evaluator."""
        from gobby.workflows.unified_evaluator import _evaluate_triggers

        event = _make_event(event_type=HookEventType.SESSION_START)
        definition = _make_definition(
            triggers={
                "on_session_start": [
                    {"action": "set_variable", "name": "key", "value": "val"},
                    {"action": "inject_context", "content": "visible"},
                ]
            },
        )

        result = _evaluate_triggers(event, definition, {})
        assert result == ["visible"]
