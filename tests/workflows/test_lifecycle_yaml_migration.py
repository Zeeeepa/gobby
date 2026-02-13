"""Tests for lifecycle YAML migration to unified format."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

WORKFLOW_DIR = Path(__file__).parent.parent.parent / "src/gobby/install/shared/workflows"
LIFECYCLE_DIR = WORKFLOW_DIR / "lifecycle"


class TestSessionLifecycleUnifiedFormat:
    """Tests for session-lifecycle.yaml unified format fields."""

    @pytest.mark.asyncio
    async def test_loads_with_enabled_true(self) -> None:
        """session-lifecycle.yaml loads with enabled=True."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert definition.enabled is True

    @pytest.mark.asyncio
    async def test_loads_with_priority_10(self) -> None:
        """session-lifecycle.yaml loads with priority=10."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert definition.priority == 10

    @pytest.mark.asyncio
    async def test_session_variables_contains_shared_state(self) -> None:
        """session-lifecycle.yaml session_variables contains shared state."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("session-lifecycle")
        assert definition is not None
        sv = definition.session_variables
        # These shared variables should be in session_variables
        assert "unlocked_tools" in sv
        assert "servers_listed" in sv
        assert "listed_servers" in sv
        assert "pre_existing_errors_triaged" in sv
        assert "stop_attempts" in sv

    @pytest.mark.asyncio
    async def test_variables_contains_workflow_scoped(self) -> None:
        """session-lifecycle.yaml variables contains workflow-scoped settings."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("session-lifecycle")
        assert definition is not None
        v = definition.variables
        # Behavior config remains in workflow variables
        assert "debug_echo_context" in v
        assert "require_task_before_edit" in v
        assert "require_uv" in v


class TestHeadlessLifecycleUnifiedFormat:
    """Tests for headless-lifecycle.yaml unified format fields."""

    @pytest.mark.asyncio
    async def test_loads_with_enabled_true(self) -> None:
        """headless-lifecycle.yaml loads with enabled=True."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("headless-lifecycle")
        assert definition is not None
        assert definition.enabled is True

    @pytest.mark.asyncio
    async def test_loads_with_priority_10(self) -> None:
        """headless-lifecycle.yaml loads with priority=10."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("headless-lifecycle")
        assert definition is not None
        assert definition.priority == 10

    @pytest.mark.asyncio
    async def test_session_variables_contains_shared_state(self) -> None:
        """headless-lifecycle.yaml session_variables contains shared state."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("headless-lifecycle")
        assert definition is not None
        sv = definition.session_variables
        assert "unlocked_tools" in sv
        assert "servers_listed" in sv
        assert "pre_existing_errors_triaged" in sv
        assert "stop_attempts" in sv


class TestLifecycleBackwardCompat:
    """Tests for backward compatibility of lifecycle directory."""

    @pytest.mark.asyncio
    async def test_lifecycle_subdir_still_discovered(self) -> None:
        """Workflows in lifecycle/ subdirectory are still discovered."""
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader(workflow_dirs=[WORKFLOW_DIR])
        definition = await loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert definition.type == "lifecycle"
