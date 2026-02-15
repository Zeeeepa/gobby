"""Tests for activate_workflow with resume parameter.

These tests verify that activate_workflow supports the resume=True flag to:
1. Idempotently return success if the workflow is already active
2. Merge provided variables into the existing active state
3. Start a new workflow if none is active (standard activation)
4. Prevent resuming a different workflow than what is active
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.workflows import create_workflows_registry
from gobby.workflows.definitions import WorkflowDefinition, WorkflowStep

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock()


@pytest.fixture
def mock_state_manager():
    """Create a mock workflow state manager."""
    return MagicMock()


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    manager = MagicMock()
    # Make resolve_session_reference return the input unchanged (for testing)
    manager.resolve_session_reference.side_effect = lambda ref, project_id=None: ref
    return manager


@pytest.fixture
def mock_loader():
    """Create a mock workflow loader with async load_workflow."""
    loader = MagicMock()
    loader.global_dirs = []
    loader.load_workflow = AsyncMock()
    return loader


@pytest.fixture
def registry(mock_loader, mock_state_manager, mock_session_manager, mock_db):
    """Create workflow registry for testing."""
    with (
        patch("gobby.mcp_proxy.tools.workflows.WorkflowInstanceManager", return_value=None),
        patch("gobby.mcp_proxy.tools.workflows.SessionVariableManager", return_value=None),
    ):
        return create_workflows_registry(
            loader=mock_loader,
            state_manager=mock_state_manager,
            session_manager=mock_session_manager,
            db=mock_db,
        )


async def call_tool(registry, tool_name: str, **kwargs) -> Any:
    """Helper to call a tool from the registry."""
    tool = registry._tools.get(tool_name)
    if not tool:
        raise ValueError(f"Tool '{tool_name}' not found")
    return await tool.func(**kwargs)


class TestActivateWorkflowResume:
    """Tests for activate_workflow with resume parameter."""

    @pytest.fixture
    def active_workflow_state(self):
        """Create a mock active workflow state."""
        mock_state = MagicMock()
        mock_state.workflow_name = "test-workflow"
        mock_state.step = "work"
        mock_state.variables = {"existing_var": "value"}
        mock_state.session_id = "test-session"
        return mock_state

    @pytest.fixture
    def workflow_def(self):
        """Create a mock workflow definition (enabled=False for on-demand)."""
        return WorkflowDefinition(
            name="test-workflow",
            enabled=False,
            steps=[WorkflowStep(name="start"), WorkflowStep(name="work")],
            variables={"default_var": "default"},
        )

    @pytest.mark.asyncio
    async def test_resume_active_workflow_success(
        self, registry, mock_loader, mock_state_manager, active_workflow_state, workflow_def
    ) -> None:
        """Verify resume=True succeeds when workflow is already active."""
        # Setup state manager to return active state
        mock_state_manager.get_state.return_value = active_workflow_state
        mock_loader.load_workflow.return_value = workflow_def

        result = await call_tool(
            registry,
            "activate_workflow",
            name="test-workflow",
            session_id="test-session",
            resume=True,
        )

        assert result["success"] is True
        assert result["workflow"] == "test-workflow"
        assert result["step"] == "work"
        assert result.get("resumed") is True
        # Variables should be preserved
        assert result["variables"]["existing_var"] == "value"

        # No new variables were provided, so state should not have been saved
        mock_state_manager.save_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_active_workflow_merges_variables(
        self, registry, mock_loader, mock_state_manager, active_workflow_state, workflow_def
    ) -> None:
        """Verify resume=True merges new variables into existing state."""
        mock_state_manager.get_state.return_value = active_workflow_state
        mock_loader.load_workflow.return_value = workflow_def

        result = await call_tool(
            registry,
            "activate_workflow",
            name="test-workflow",
            session_id="test-session",
            resume=True,
            variables={"new_var": "new_value", "existing_var": "updated_value"},
        )

        assert result["success"] is True
        assert result["variables"]["new_var"] == "new_value"
        assert result["variables"]["existing_var"] == "updated_value"

        # Verify state was updated
        assert active_workflow_state.variables["new_var"] == "new_value"
        assert active_workflow_state.variables["existing_var"] == "updated_value"
        mock_state_manager.save_state.assert_called_with(active_workflow_state)

    @pytest.mark.asyncio
    async def test_resume_false_reactivates(
        self, registry, mock_loader, mock_state_manager, active_workflow_state, workflow_def
    ) -> None:
        """Verify resume=False (default) re-initializes workflow when already active."""
        mock_state_manager.get_state.return_value = active_workflow_state
        mock_loader.load_workflow.return_value = workflow_def

        # Without resume=True, workflow is re-initialized at first step
        result = await call_tool(
            registry,
            "activate_workflow",
            name="test-workflow",
            session_id="test-session",
        )

        assert result["success"] is True
        assert result["step"] == "start"  # Reset to first step
        mock_state_manager.save_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_mismatch_activates_new(
        self, registry, mock_loader, mock_state_manager, active_workflow_state, workflow_def
    ) -> None:
        """Verify resume=True with different workflow name activates the new workflow."""
        mock_state_manager.get_state.return_value = active_workflow_state
        mock_loader.load_workflow.return_value = workflow_def

        result = await call_tool(
            registry,
            "activate_workflow",
            name="other-workflow",  # Mismatch - different name
            session_id="test-session",
            resume=True,
        )

        # Mismatch doesn't resume, but still activates the new workflow
        assert result["success"] is True
        assert result["workflow"] == "other-workflow"
        mock_state_manager.save_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_no_active_starts_fresh(
        self, registry, mock_loader, mock_state_manager, workflow_def
    ) -> None:
        """Verify resume=True starts fresh if no workflow is active."""
        mock_state_manager.get_state.return_value = None
        mock_loader.load_workflow.return_value = workflow_def

        result = await call_tool(
            registry,
            "activate_workflow",
            name="test-workflow",
            session_id="test-session",
            resume=True,
        )

        assert result["success"] is True
        assert result["step"] == "start"  # Initial step
        mock_state_manager.save_state.assert_called_once()
