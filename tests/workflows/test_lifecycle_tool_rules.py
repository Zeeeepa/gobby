"""Tests for tool_rules field on WorkflowDefinition and lifecycle evaluation.

Verifies: tool_rules field accepted on WorkflowDefinition, evaluated via
block_tools() on BEFORE_TOOL events in lifecycle evaluator, interacts
correctly with trigger-based block_tools actions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState

pytestmark = pytest.mark.unit


# =============================================================================
# Model tests: tool_rules field on WorkflowDefinition
# =============================================================================


class TestToolRulesField:
    def test_default_empty(self) -> None:
        """WorkflowDefinition.tool_rules defaults to empty list."""
        defn = WorkflowDefinition(name="test", type="lifecycle")
        assert defn.tool_rules == []

    def test_accepts_rules_list(self) -> None:
        """WorkflowDefinition accepts a list of rule dicts."""
        rules = [
            {"tools": ["Edit", "Write"], "reason": "No editing allowed"},
            {"mcp_tools": ["gobby-tasks:close_task"], "reason": "No closing"},
        ]
        defn = WorkflowDefinition(name="test", type="lifecycle", tool_rules=rules)
        assert len(defn.tool_rules) == 2
        assert defn.tool_rules[0]["tools"] == ["Edit", "Write"]
        assert defn.tool_rules[1]["mcp_tools"] == ["gobby-tasks:close_task"]

    def test_with_when_condition(self) -> None:
        """tool_rules entries can include when conditions."""
        rules = [
            {
                "tools": ["Edit"],
                "when": "not task_claimed",
                "reason": "Claim a task first",
            }
        ]
        defn = WorkflowDefinition(name="test", type="lifecycle", tool_rules=rules)
        assert defn.tool_rules[0]["when"] == "not task_claimed"


# =============================================================================
# Lifecycle evaluation tests: tool_rules evaluated on BEFORE_TOOL
# =============================================================================


def _make_event(
    tool_name: str = "Edit",
    tool_input: dict[str, Any] | None = None,
    session_id: str = "test-session",
    event_type: HookEventType = HookEventType.BEFORE_TOOL,
) -> HookEvent:
    """Create a HookEvent (defaults to BEFORE_TOOL)."""
    return HookEvent(
        event_type=event_type,
        session_id=session_id,
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data={
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        },
        metadata={"_platform_session_id": session_id},
    )


def _make_state(session_id: str = "test-session", **variables: Any) -> WorkflowState:
    """Create a WorkflowState with given variables."""
    return WorkflowState(
        session_id=session_id,
        workflow_name="test-wf",
        step="global",
        step_entered_at=datetime.now(UTC),
        variables=variables,
    )


def _make_workflow(
    tool_rules: list[dict[str, Any]] | None = None,
    triggers: dict[str, list[dict[str, Any]]] | None = None,
) -> WorkflowDefinition:
    """Create a WorkflowDefinition with optional tool_rules and triggers."""
    return WorkflowDefinition(
        name="test-wf",
        type="lifecycle",
        tool_rules=tool_rules or [],
        triggers=triggers or {},
    )


def _mock_state_manager(state: WorkflowState | None = None) -> MagicMock:
    """Create a mock WorkflowStateManager."""
    mgr = MagicMock()
    mgr.get_state.return_value = state
    mgr.save_state = MagicMock()
    mgr.merge_variables = MagicMock()
    return mgr


def _mock_action_executor() -> MagicMock:
    """Create a mock ActionExecutor."""
    executor = MagicMock()
    executor.db = None
    executor.session_manager = MagicMock()
    executor.session_manager.get.return_value = None
    executor.template_engine = None
    executor.llm_service = None
    executor.transcript_processor = None
    executor.config = None
    executor.tool_proxy_getter = None
    executor.memory_manager = None
    executor.memory_sync_manager = None
    executor.task_sync_manager = None
    executor.session_task_manager = None
    executor.skill_manager = None
    executor.execute = AsyncMock(return_value={})
    return executor


def _mock_evaluator() -> MagicMock:
    """Create a mock ConditionEvaluator."""
    evaluator = MagicMock()
    evaluator.evaluate.return_value = True
    return evaluator


class TestToolRulesLifecycleEvaluation:
    @pytest.mark.asyncio
    async def test_tool_rules_blocks_matching_tool(self) -> None:
        """tool_rules should block a matching tool via block_tools()."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        workflow = _make_workflow(tool_rules=[{"tools": ["Edit"], "reason": "Editing is blocked"}])
        event = _make_event(tool_name="Edit")
        state = _make_state()
        state_mgr = _mock_state_manager(state)

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event,
            context_data={},
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),
        )

        assert response.decision == "block"
        assert "Editing is blocked" in (response.reason or "")

    @pytest.mark.asyncio
    async def test_tool_rules_allows_non_matching_tool(self) -> None:
        """tool_rules should not block a non-matching tool."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        workflow = _make_workflow(tool_rules=[{"tools": ["Write"], "reason": "Writing is blocked"}])
        event = _make_event(tool_name="Edit")
        state = _make_state()
        state_mgr = _mock_state_manager(state)

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event,
            context_data={},
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),
        )

        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_tool_rules_when_condition_evaluated(self) -> None:
        """tool_rules with when condition should only block when condition is true."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        workflow = _make_workflow(
            tool_rules=[
                {
                    "tools": ["Edit"],
                    "when": "not task_claimed",
                    "reason": "Claim a task first",
                }
            ]
        )
        event = _make_event(tool_name="Edit")
        # task_claimed=True -> when condition "not task_claimed" is False -> should allow
        state = _make_state(task_claimed=True)
        state_mgr = _mock_state_manager(state)

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event,
            context_data={"task_claimed": True},
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),
        )

        # block_tools evaluates the when condition itself; with task_claimed=True,
        # "not task_claimed" -> False, so the rule shouldn't match
        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_tool_rules_and_triggers_both_apply(self) -> None:
        """Both tool_rules and trigger-based block_tools should apply."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        # tool_rules blocks Write, trigger blocks Edit
        workflow = _make_workflow(
            tool_rules=[{"tools": ["Write"], "reason": "tool_rules: Write blocked"}],
            triggers={
                "on_before_tool": [
                    {
                        "action": "block_tools",
                        "rules": [{"tools": ["Edit"], "reason": "trigger: Edit blocked"}],
                    }
                ]
            },
        )

        # Test that tool_rules blocks Write
        event_write = _make_event(tool_name="Write")
        state = _make_state()
        state_mgr = _mock_state_manager(state)
        executor = _mock_action_executor()
        # The trigger action for Edit won't fire since we're testing Write
        executor.execute = AsyncMock(return_value={})

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event_write,
            context_data={},
            state_manager=state_mgr,
            action_executor=executor,
            evaluator=_mock_evaluator(),
        )

        assert response.decision == "block"
        assert "tool_rules: Write blocked" in (response.reason or "")

    @pytest.mark.asyncio
    async def test_empty_tool_rules_is_noop(self) -> None:
        """Empty tool_rules should not affect evaluation."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        workflow = _make_workflow(tool_rules=[])
        event = _make_event(tool_name="Edit")
        state = _make_state()
        state_mgr = _mock_state_manager(state)

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event,
            context_data={},
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),
        )

        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_tool_rules_blocks_mcp_tool(self) -> None:
        """tool_rules should block MCP tools via mcp_tools patterns."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        workflow = _make_workflow(
            tool_rules=[
                {
                    "mcp_tools": ["gobby-tasks:close_task"],
                    "reason": "Cannot close tasks",
                }
            ]
        )
        # MCP tools come in as call_tool with server_name/tool_name in tool_input
        event = _make_event(
            tool_name="mcp__gobby__call_tool",
            tool_input={"server_name": "gobby-tasks", "tool_name": "close_task"},
        )
        state = _make_state()
        state_mgr = _mock_state_manager(state)

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event,
            context_data={},
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),
        )

        assert response.decision == "block"
        assert "Cannot close tasks" in (response.reason or "")

    @pytest.mark.asyncio
    async def test_tool_rules_only_on_before_tool(self) -> None:
        """tool_rules should only be evaluated on BEFORE_TOOL events, not others."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        workflow = _make_workflow(tool_rules=[{"tools": ["Edit"], "reason": "Editing is blocked"}])
        # Use SESSION_START event instead of BEFORE_TOOL
        event = _make_event(
            event_type=HookEventType.SESSION_START,
        )
        state = _make_state()
        state_mgr = _mock_state_manager(state)

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event,
            context_data={},
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),
        )

        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_tool_rules_runs_before_triggers(self) -> None:
        """tool_rules should be evaluated before trigger-based actions."""
        from gobby.workflows.lifecycle_evaluator import evaluate_workflow_triggers

        # tool_rules blocks Edit, and trigger also has an inject_context action
        # If tool_rules runs first, it should block before the trigger fires
        workflow = _make_workflow(
            tool_rules=[{"tools": ["Edit"], "reason": "Blocked by tool_rules"}],
            triggers={
                "on_before_tool": [
                    {
                        "action": "inject_context",
                        "template": "This should not be injected",
                    }
                ]
            },
        )
        event = _make_event(tool_name="Edit")
        state = _make_state()
        state_mgr = _mock_state_manager(state)
        executor = _mock_action_executor()

        response = await evaluate_workflow_triggers(
            workflow=workflow,
            event=event,
            context_data={},
            state_manager=state_mgr,
            action_executor=executor,
            evaluator=_mock_evaluator(),
        )

        assert response.decision == "block"
        assert "Blocked by tool_rules" in (response.reason or "")
        # The trigger action should NOT have been called since tool_rules blocked first
        executor.execute.assert_not_called()
