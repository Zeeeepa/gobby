"""Tests for lifecycle YAML migration to unified format."""

from __future__ import annotations

import pytest

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit


class TestSessionLifecycleUnifiedFormat:
    """Tests for session-lifecycle.yaml unified format fields."""

    @pytest.mark.asyncio
    async def test_loads_with_enabled_true(self, db_loader: WorkflowLoader) -> None:
        """session-lifecycle.yaml loads with enabled=True."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert definition.enabled is True

    @pytest.mark.asyncio
    async def test_loads_with_priority_10(self, db_loader: WorkflowLoader) -> None:
        """session-lifecycle.yaml loads with priority=10."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert definition.priority == 10

    @pytest.mark.asyncio
    async def test_session_variables_contains_shared_state(
        self, db_loader: WorkflowLoader
    ) -> None:
        """session-lifecycle.yaml session_variables contains shared state."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        sv = definition.session_variables
        # These shared variables should be in session_variables
        assert "unlocked_tools" in sv
        assert "servers_listed" in sv
        assert "listed_servers" in sv
        assert "pre_existing_errors_triaged" in sv
        assert "stop_attempts" in sv

    @pytest.mark.asyncio
    async def test_variables_contains_workflow_scoped(self, db_loader: WorkflowLoader) -> None:
        """session-lifecycle.yaml variables contains workflow-scoped settings."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        v = definition.variables
        # Behavior config remains in workflow variables
        assert "debug_echo_context" in v
        assert "require_task_before_edit" in v
        assert "require_uv" in v


class TestHeadlessLifecycleUnifiedFormat:
    """Tests for headless-lifecycle.yaml unified format fields."""

    @pytest.mark.asyncio
    async def test_loads_with_enabled_true(self, db_loader: WorkflowLoader) -> None:
        """headless-lifecycle.yaml loads with enabled=True."""
        definition = await db_loader.load_workflow("headless-lifecycle")
        assert definition is not None
        assert definition.enabled is True

    @pytest.mark.asyncio
    async def test_loads_with_priority_10(self, db_loader: WorkflowLoader) -> None:
        """headless-lifecycle.yaml loads with priority=10."""
        definition = await db_loader.load_workflow("headless-lifecycle")
        assert definition is not None
        assert definition.priority == 10

    @pytest.mark.asyncio
    async def test_session_variables_contains_shared_state(
        self, db_loader: WorkflowLoader
    ) -> None:
        """headless-lifecycle.yaml session_variables contains shared state."""
        definition = await db_loader.load_workflow("headless-lifecycle")
        assert definition is not None
        sv = definition.session_variables
        assert "unlocked_tools" in sv
        assert "servers_listed" in sv
        assert "pre_existing_errors_triaged" in sv
        assert "stop_attempts" in sv


class TestLifecycleBackwardCompat:
    """Tests for backward compatibility — lifecycle workflows now use enabled=True."""

    @pytest.mark.asyncio
    async def test_lifecycle_workflow_is_enabled(self, db_loader: WorkflowLoader) -> None:
        """Lifecycle workflows are discovered and have enabled=True."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert definition.enabled is True
