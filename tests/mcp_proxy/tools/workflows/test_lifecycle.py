"""Tests for workflow lifecycle MCP tools (activate, end) with multi-workflow support."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.definitions import WorkflowDefinition, WorkflowInstance, WorkflowState

pytestmark = pytest.mark.unit


def _make_definition(
    name: str = "test-wf",
    wf_type: str = "step",
    variables: dict | None = None,
    session_variables: dict | None = None,
    steps: list | None = None,
) -> WorkflowDefinition:
    """Create a minimal WorkflowDefinition for testing."""
    from gobby.workflows.definitions import WorkflowStep

    return WorkflowDefinition(
        name=name,
        type=wf_type,
        variables=variables or {},
        session_variables=session_variables or {},
        steps=steps or [WorkflowStep(name="start"), WorkflowStep(name="work")],
    )


def _make_mocks(
    existing_state: WorkflowState | None = None,
    definition: WorkflowDefinition | None = None,
) -> dict[str, Any]:
    """Create mock dependencies for lifecycle functions."""
    loader = MagicMock()
    loader.load_workflow = AsyncMock(return_value=definition or _make_definition())

    state_manager = MagicMock()
    state_manager.get_state.return_value = existing_state

    session_manager = MagicMock()
    session_manager.resolve_session_reference.return_value = "uuid-session-1"

    instance_manager = MagicMock()
    instance_manager.get_instance.return_value = None

    session_var_manager = MagicMock()

    db = MagicMock()

    return {
        "loader": loader,
        "state_manager": state_manager,
        "session_manager": session_manager,
        "instance_manager": instance_manager,
        "session_var_manager": session_var_manager,
        "db": db,
    }


class TestActivateWorkflowMultiWorkflow:
    """Tests for activate_workflow with multi-workflow support."""

    @pytest.mark.asyncio
    async def test_activate_creates_workflow_instance(self) -> None:
        """activate_workflow() creates a workflow_instances row with enabled=True."""
        from gobby.mcp_proxy.tools.workflows._lifecycle import activate_workflow

        mocks = _make_mocks()

        result = await activate_workflow(
            mocks["loader"],
            mocks["state_manager"],
            mocks["session_manager"],
            mocks["db"],
            name="test-wf",
            session_id="#1",
            instance_manager=mocks["instance_manager"],
            session_var_manager=mocks["session_var_manager"],
        )

        assert result["success"] is True
        # Verify instance was saved
        mocks["instance_manager"].save_instance.assert_called_once()
        saved_instance = mocks["instance_manager"].save_instance.call_args[0][0]
        assert isinstance(saved_instance, WorkflowInstance)
        assert saved_instance.enabled is True
        assert saved_instance.workflow_name == "test-wf"
        assert saved_instance.session_id == "uuid-session-1"

    @pytest.mark.asyncio
    async def test_activate_multiple_workflows_same_session(self) -> None:
        """activate_workflow() can activate multiple workflows on the same session."""
        from gobby.mcp_proxy.tools.workflows._lifecycle import activate_workflow

        # First workflow already active
        existing_state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="workflow-a",
            step="work",
        )
        mocks = _make_mocks(existing_state=existing_state)

        # Activate second workflow
        wf_b = _make_definition(name="workflow-b")
        mocks["loader"].load_workflow = AsyncMock(side_effect=[
            _make_definition(name="workflow-a"),  # lookup for existing
            wf_b,  # lookup for new
        ])

        result = await activate_workflow(
            mocks["loader"],
            mocks["state_manager"],
            mocks["session_manager"],
            mocks["db"],
            name="workflow-b",
            session_id="#1",
            instance_manager=mocks["instance_manager"],
            session_var_manager=mocks["session_var_manager"],
        )

        assert result["success"] is True
        assert result["workflow"] == "workflow-b"

    @pytest.mark.asyncio
    async def test_activate_merges_session_variables(self) -> None:
        """activate_workflow() merges session_variables declarations into session_variables table."""
        from gobby.mcp_proxy.tools.workflows._lifecycle import activate_workflow

        definition = _make_definition(
            session_variables={"shared_flag": True, "counter": 0},
        )
        mocks = _make_mocks(definition=definition)

        result = await activate_workflow(
            mocks["loader"],
            mocks["state_manager"],
            mocks["session_manager"],
            mocks["db"],
            name="test-wf",
            session_id="#1",
            instance_manager=mocks["instance_manager"],
            session_var_manager=mocks["session_var_manager"],
        )

        assert result["success"] is True
        mocks["session_var_manager"].merge_variables.assert_called_once_with(
            "uuid-session-1", {"shared_flag": True, "counter": 0}
        )


class TestEndWorkflowMultiWorkflow:
    """Tests for end_workflow with multi-workflow support."""

    @pytest.mark.asyncio
    async def test_end_specific_workflow(self) -> None:
        """end_workflow(workflow='name') sets enabled=False on specific instance."""
        from gobby.mcp_proxy.tools.workflows._lifecycle import end_workflow

        existing_state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="test-wf",
            step="work",
        )
        mocks = _make_mocks(existing_state=existing_state)

        result = await end_workflow(
            mocks["loader"],
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            workflow="test-wf",
            instance_manager=mocks["instance_manager"],
        )

        assert result["success"] is True
        mocks["instance_manager"].set_enabled.assert_called_once_with(
            "uuid-session-1", "test-wf", False
        )

    @pytest.mark.asyncio
    async def test_end_clears_workflow_variables_preserves_session(self) -> None:
        """end_workflow() clears workflow-scoped variables but preserves session variables."""
        from gobby.mcp_proxy.tools.workflows._lifecycle import end_workflow

        definition = _make_definition(variables={"wf_var": "value"})
        existing_state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="test-wf",
            step="work",
            variables={"wf_var": "value", "session_task": "some-uuid"},
        )
        mocks = _make_mocks(existing_state=existing_state, definition=definition)

        result = await end_workflow(
            mocks["loader"],
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            workflow="test-wf",
            instance_manager=mocks["instance_manager"],
        )

        assert result["success"] is True
        # Workflow variable should be cleared, session_task preserved
        saved_state = mocks["state_manager"].save_state.call_args[0][0]
        assert "wf_var" not in saved_state.variables
        assert "session_task" in saved_state.variables

    @pytest.mark.asyncio
    async def test_end_does_not_affect_other_workflows(self) -> None:
        """end_workflow() does not affect other active workflows."""
        from gobby.mcp_proxy.tools.workflows._lifecycle import end_workflow

        existing_state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="workflow-a",
            step="work",
        )
        mocks = _make_mocks(existing_state=existing_state)

        result = await end_workflow(
            mocks["loader"],
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            workflow="workflow-a",
            instance_manager=mocks["instance_manager"],
        )

        assert result["success"] is True
        # Only workflow-a should be affected
        mocks["instance_manager"].set_enabled.assert_called_once_with(
            "uuid-session-1", "workflow-a", False
        )

    @pytest.mark.asyncio
    async def test_end_without_workflow_uses_current(self) -> None:
        """end_workflow() without workflow param uses the current active workflow."""
        from gobby.mcp_proxy.tools.workflows._lifecycle import end_workflow

        existing_state = WorkflowState(
            session_id="uuid-session-1",
            workflow_name="test-wf",
            step="work",
        )
        mocks = _make_mocks(existing_state=existing_state)

        result = await end_workflow(
            mocks["loader"],
            mocks["state_manager"],
            mocks["session_manager"],
            session_id="#1",
            instance_manager=mocks["instance_manager"],
        )

        assert result["success"] is True
        assert result["workflow"] == "test-wf"
