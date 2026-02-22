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
    async def test_session_variables_contains_shared_state(self, db_loader: WorkflowLoader) -> None:
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

    @pytest.mark.asyncio
    async def test_sources_include_sdk(self, db_loader: WorkflowLoader) -> None:
        """session-lifecycle.yaml sources include SDK sources (merged from headless-lifecycle)."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert "claude_sdk" in definition.sources
        assert "claude_sdk_web_chat" in definition.sources

    @pytest.mark.asyncio
    async def test_no_session_initialized_variable(self, db_loader: WorkflowLoader) -> None:
        """session-lifecycle.yaml no longer has _session_initialized (moved to claude-sdk-lifecycle)."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert "_session_initialized" not in definition.variables


class TestClaudeSdkLifecycle:
    """Tests for claude-sdk-lifecycle.yaml extracted workflow."""

    @pytest.mark.asyncio
    async def test_loads_with_enabled_true(self, db_loader: WorkflowLoader) -> None:
        """claude-sdk-lifecycle.yaml loads with enabled=True."""
        definition = await db_loader.load_workflow("claude-sdk-lifecycle")
        assert definition is not None
        assert definition.enabled is True

    @pytest.mark.asyncio
    async def test_priority_after_session_lifecycle(self, db_loader: WorkflowLoader) -> None:
        """claude-sdk-lifecycle.yaml has priority 11 (after session-lifecycle at 10)."""
        definition = await db_loader.load_workflow("claude-sdk-lifecycle")
        assert definition is not None
        assert definition.priority == 11

    @pytest.mark.asyncio
    async def test_sources_sdk_only(self, db_loader: WorkflowLoader) -> None:
        """claude-sdk-lifecycle.yaml only targets SDK sources."""
        definition = await db_loader.load_workflow("claude-sdk-lifecycle")
        assert definition is not None
        assert set(definition.sources) == {"claude_sdk", "claude_sdk_web_chat"}

    @pytest.mark.asyncio
    async def test_sdk_initialized_variable(self, db_loader: WorkflowLoader) -> None:
        """claude-sdk-lifecycle.yaml has _sdk_initialized guard variable."""
        definition = await db_loader.load_workflow("claude-sdk-lifecycle")
        assert definition is not None
        assert "_sdk_initialized" in definition.variables
        assert definition.variables["_sdk_initialized"] is False


class TestLifecycleBackwardCompat:
    """Tests for backward compatibility — lifecycle workflows now use enabled=True."""

    @pytest.mark.asyncio
    async def test_lifecycle_workflow_is_enabled(self, db_loader: WorkflowLoader) -> None:
        """Lifecycle workflows are discovered and have enabled=True."""
        definition = await db_loader.load_workflow("session-lifecycle")
        assert definition is not None
        assert definition.enabled is True
