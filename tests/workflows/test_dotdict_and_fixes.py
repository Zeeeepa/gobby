"""Tests for DotDict, force transition context_injected reset, and end_workflow variable persistence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.engine import DotDict

pytestmark = pytest.mark.unit


class TestDotDict:
    """DotDict must support both dot-notation and .get() access."""

    def test_dot_access(self) -> None:
        d = DotDict({"foo": "bar", "count": 42})
        assert d.foo == "bar"
        assert d.count == 42

    def test_get_access(self) -> None:
        d = DotDict({"foo": "bar"})
        assert d.get("foo") == "bar"
        assert d.get("missing") is None
        assert d.get("missing", "default") == "default"

    def test_dot_access_missing_raises(self) -> None:
        d = DotDict({"foo": "bar"})
        with pytest.raises(AttributeError):
            _ = d.missing_key

    def test_set_via_dot(self) -> None:
        d = DotDict({})
        d.new_key = "value"
        assert d["new_key"] == "value"
        assert d.get("new_key") == "value"

    def test_nested_dict_not_converted(self) -> None:
        """Nested dicts remain plain dicts (no recursive conversion)."""
        d = DotDict({"nested": {"inner": 1}})
        assert isinstance(d.nested, dict)
        assert d.nested["inner"] == 1

    def test_works_in_eval_context(self) -> None:
        """Simulate the eval pattern used in workflow transition conditions."""
        variables = DotDict({"task_claimed": True, "session_task": "abc-123"})
        # This is what transition conditions do:
        assert variables.get("task_claimed") is True
        assert variables.get("session_task") == "abc-123"
        assert variables.get("nonexistent") is None
        # Dot notation also works:
        assert variables.task_claimed is True


@pytest.mark.asyncio
class TestForceTransitionContextInjected:
    """request_step_transition(force=True) must reset context_injected."""

    async def test_force_transition_resets_context_injected(self) -> None:
        from gobby.mcp_proxy.tools.workflows._lifecycle import request_step_transition
        from gobby.workflows.definitions import WorkflowDefinition, WorkflowState, WorkflowStep

        state = WorkflowState(
            session_id="test-session-uuid",
            workflow_name="test-workflow",
            step="step_a",
            step_entered_at=datetime.now(UTC),
            step_action_count=5,
            total_action_count=10,
            artifacts={},
            observations=[],
            reflection_pending=False,
            context_injected=True,  # Already injected for current step
            variables={},
        )

        step_a = WorkflowStep(name="step_a")
        step_b = WorkflowStep(name="step_b")
        definition = WorkflowDefinition(
            name="test-workflow",
            description="test",
            steps=[step_a, step_b],
        )

        loader = AsyncMock()
        loader.load_workflow.return_value = definition

        state_manager = MagicMock()
        state_manager.get_state.return_value = state

        session_manager = MagicMock()
        session_manager.get_by_ref.return_value = MagicMock(id="test-session-uuid")

        result = await request_step_transition(
            loader=loader,
            state_manager=state_manager,
            session_manager=session_manager,
            to_step="step_b",
            session_id="#1",
            force=True,
        )

        assert result["success"] is True
        assert result["to_step"] == "step_b"
        # Key assertion: context_injected must be False so on_enter runs
        assert state.context_injected is False
        assert state.step_action_count == 0


@pytest.mark.asyncio
class TestEndWorkflowVariablePersistence:
    """end_workflow must save_state before delete_state to persist variable cleanup."""

    async def test_end_workflow_saves_before_delete(self) -> None:
        from gobby.mcp_proxy.tools.workflows._lifecycle import end_workflow
        from gobby.workflows.definitions import WorkflowDefinition, WorkflowState

        state = WorkflowState(
            session_id="test-session-uuid",
            workflow_name="test-workflow",
            step="work",
            step_entered_at=datetime.now(UTC),
            step_action_count=0,
            total_action_count=0,
            artifacts={},
            observations=[],
            reflection_pending=False,
            context_injected=True,
            variables={
                "session_task": "task-123",  # workflow-declared variable
                "plan_mode": False,  # workflow-declared variable
                "unlocked_tools": [],  # lifecycle variable (not in workflow)
            },
        )

        definition = WorkflowDefinition(
            name="test-workflow",
            description="test",
            steps=[],
            variables={"session_task": "", "plan_mode": False},
        )

        loader = AsyncMock()
        loader.load_workflow.return_value = definition

        state_manager = MagicMock()
        state_manager.get_state.return_value = state

        session_manager = MagicMock()
        session_manager.get_by_ref.return_value = MagicMock(id="test-session-uuid")

        # Track call order to verify save_state is called before delete_state
        call_order: list[str] = []
        state_manager.save_state.side_effect = lambda s: call_order.append("save")
        state_manager.delete_state.side_effect = lambda sid: call_order.append("delete")

        result = await end_workflow(
            loader=loader,
            state_manager=state_manager,
            session_manager=session_manager,
            session_id="#1",
        )

        assert result["success"] is True
        # Workflow-declared variables should be popped
        assert "session_task" not in state.variables
        assert "plan_mode" not in state.variables
        # Lifecycle variable should be preserved
        assert "unlocked_tools" in state.variables
        # save_state must be called BEFORE delete_state
        assert call_order == ["save", "delete"]
