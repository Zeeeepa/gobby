"""Tests for observer evaluation wired into lifecycle_evaluator.

Verifies: observers fire on matching events via evaluate_all_lifecycle_workflows,
YAML observers set variables, behavior observers call registered functions,
state changes persist, non-matching events are skipped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.definitions import Observer, WorkflowDefinition, WorkflowState

pytestmark = pytest.mark.unit


def _make_event(
    event_type: HookEventType = HookEventType.AFTER_TOOL,
    tool_name: str = "Edit",
    tool_input: dict[str, Any] | None = None,
    session_id: str = "test-session",
) -> HookEvent:
    return HookEvent(
        event_type=event_type,
        session_id="ext-123",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data={
            "tool_name": tool_name,
            "tool_input": tool_input or {},
        },
        metadata={"_platform_session_id": session_id},
    )


def _make_workflow(
    observers: list[Observer] | None = None,
    triggers: dict[str, list[dict[str, Any]]] | None = None,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        name="test-lifecycle",
        type="lifecycle",
        observers=observers or [],
        triggers=triggers or {},
    )


class _MockDiscovered:
    """Mimics a discovered workflow object."""

    def __init__(self, workflow: WorkflowDefinition) -> None:
        self.name = workflow.name
        self.definition = workflow
        self.priority = 0
        self.is_project = False
        self.path = "/fake/path"


def _mock_loader(workflows: list[WorkflowDefinition]) -> MagicMock:
    loader = MagicMock()
    discovered = [_MockDiscovered(w) for w in workflows]
    loader.discover_lifecycle_workflows = AsyncMock(return_value=discovered)
    return loader


def _mock_state_manager(state: WorkflowState | None = None) -> MagicMock:
    mgr = MagicMock()
    mgr.get_state.return_value = state
    mgr.save_state = MagicMock()
    mgr.merge_variables = MagicMock()
    return mgr


def _mock_action_executor() -> MagicMock:
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
    evaluator = MagicMock()
    evaluator.evaluate.return_value = True
    return evaluator


class TestObserverEvaluationInLifecycle:
    @pytest.mark.asyncio
    async def test_yaml_observer_sets_variable(self) -> None:
        """YAML observer in lifecycle workflow sets variable on matching event."""
        from gobby.workflows.lifecycle_evaluator import evaluate_all_lifecycle_workflows
        from gobby.workflows.observers import ObserverEngine

        workflow = _make_workflow(
            observers=[
                Observer(
                    name="track_edits",
                    on="after_tool",
                    match={"tool": "Edit"},
                    set={"edit_tracked": "true"},
                ),
            ]
        )

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-lifecycle",
            step="global",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        state_mgr = _mock_state_manager(state)

        event = _make_event(event_type=HookEventType.AFTER_TOOL, tool_name="Edit")

        response = await evaluate_all_lifecycle_workflows(
            event=event,
            loader=_mock_loader([workflow]),
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),

            check_premature_stop_fn=AsyncMock(return_value=None),
            observer_engine=ObserverEngine(),
        )

        assert response.decision == "allow"
        # Variable should be set on the state
        assert state.variables.get("edit_tracked") is True

    @pytest.mark.asyncio
    async def test_observer_not_fired_on_non_matching_event(self) -> None:
        """Observer should not fire when event type doesn't match."""
        from gobby.workflows.lifecycle_evaluator import evaluate_all_lifecycle_workflows
        from gobby.workflows.observers import ObserverEngine

        workflow = _make_workflow(
            observers=[
                Observer(
                    name="track_edits",
                    on="after_tool",
                    match={"tool": "Edit"},
                    set={"edit_tracked": "true"},
                ),
            ]
        )

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-lifecycle",
            step="global",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        state_mgr = _mock_state_manager(state)

        # Use BEFORE_TOOL instead of AFTER_TOOL
        event = _make_event(event_type=HookEventType.BEFORE_TOOL, tool_name="Edit")

        await evaluate_all_lifecycle_workflows(
            event=event,
            loader=_mock_loader([workflow]),
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),

            check_premature_stop_fn=AsyncMock(return_value=None),
            observer_engine=ObserverEngine(),
        )

        assert "edit_tracked" not in state.variables

    @pytest.mark.asyncio
    async def test_behavior_observer_calls_registered_fn(self) -> None:
        """Behavior observer triggers registered behavior function."""
        from gobby.workflows.lifecycle_evaluator import evaluate_all_lifecycle_workflows
        from gobby.workflows.observers import BehaviorRegistry, ObserverEngine

        called = {"count": 0}

        async def mock_behavior(event: Any, state: Any, **kwargs: Any) -> None:
            called["count"] += 1
            state.variables["behavior_ran"] = True

        registry = BehaviorRegistry()
        registry.register("mock_behavior", mock_behavior)

        workflow = _make_workflow(
            observers=[Observer(name="test", behavior="mock_behavior")]
        )

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-lifecycle",
            step="global",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        state_mgr = _mock_state_manager(state)

        event = _make_event(event_type=HookEventType.AFTER_TOOL)

        await evaluate_all_lifecycle_workflows(
            event=event,
            loader=_mock_loader([workflow]),
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),

            check_premature_stop_fn=AsyncMock(return_value=None),
            observer_engine=ObserverEngine(behavior_registry=registry),
        )

        assert called["count"] == 1
        assert state.variables.get("behavior_ran") is True

    @pytest.mark.asyncio
    async def test_state_changes_persisted(self) -> None:
        """State changes from observers should be persisted via merge_variables."""
        from gobby.workflows.lifecycle_evaluator import evaluate_all_lifecycle_workflows
        from gobby.workflows.observers import ObserverEngine

        workflow = _make_workflow(
            observers=[
                Observer(
                    name="set_var",
                    on="after_tool",
                    set={"new_var": "value"},
                ),
            ]
        )

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-lifecycle",
            step="global",
            step_entered_at=datetime.now(UTC),
            variables={"existing": "kept"},
        )
        state_mgr = _mock_state_manager(state)

        event = _make_event(event_type=HookEventType.AFTER_TOOL)

        await evaluate_all_lifecycle_workflows(
            event=event,
            loader=_mock_loader([workflow]),
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),

            check_premature_stop_fn=AsyncMock(return_value=None),
            observer_engine=ObserverEngine(),
        )

        # merge_variables should have been called with the new variable
        state_mgr.merge_variables.assert_called()

    @pytest.mark.asyncio
    async def test_no_observer_engine_is_noop(self) -> None:
        """When no observer_engine is provided, observers are silently skipped."""
        from gobby.workflows.lifecycle_evaluator import evaluate_all_lifecycle_workflows

        workflow = _make_workflow(
            observers=[
                Observer(name="track", on="after_tool", set={"var": "val"}),
            ]
        )

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-lifecycle",
            step="global",
            step_entered_at=datetime.now(UTC),
            variables={},
        )
        state_mgr = _mock_state_manager(state)

        event = _make_event(event_type=HookEventType.AFTER_TOOL)

        # No observer_engine parameter — should not raise
        await evaluate_all_lifecycle_workflows(
            event=event,
            loader=_mock_loader([workflow]),
            state_manager=state_mgr,
            action_executor=_mock_action_executor(),
            evaluator=_mock_evaluator(),

            check_premature_stop_fn=AsyncMock(return_value=None),
        )

        # Variable should NOT be set since no engine was provided
        assert "var" not in state.variables
