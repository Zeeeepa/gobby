"""Tests for lifecycle YAML migration to unified format."""

from __future__ import annotations

import pytest

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit


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


