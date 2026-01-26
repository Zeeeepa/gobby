"""
Tests for SpawnExecutor unified spawn dispatch.
"""

from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.spawn_executor import (
    SpawnRequest,
    SpawnResult,
    execute_spawn,
)


class TestSpawnRequest:
    """Tests for SpawnRequest dataclass."""

    def test_spawn_request_fields(self):
        """Test SpawnRequest has all required fields."""
        request = SpawnRequest(
            prompt="Test prompt",
            cwd="/path/to/project",
            mode="terminal",
            provider="claude",
            terminal="auto",
            session_id="session-123",
            run_id="run-456",
            parent_session_id="parent-789",
            project_id="proj-abc",
        )

        assert request.prompt == "Test prompt"
        assert request.cwd == "/path/to/project"
        assert request.mode == "terminal"
        assert request.provider == "claude"
        assert request.terminal == "auto"
        assert request.session_id == "session-123"
        assert request.run_id == "run-456"
        assert request.parent_session_id == "parent-789"
        assert request.project_id == "proj-abc"

    def test_spawn_request_optional_fields(self):
        """Test SpawnRequest optional fields have defaults."""
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="terminal",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
        )

        assert request.workflow is None
        assert request.worktree_id is None
        assert request.clone_id is None
        assert request.agent_depth == 0
        assert request.max_agent_depth == 3


class TestSpawnResult:
    """Tests for SpawnResult dataclass."""

    def test_spawn_result_success(self):
        """Test successful SpawnResult."""
        result = SpawnResult(
            success=True,
            run_id="run-123",
            child_session_id="child-456",
            status="pending",
            pid=12345,
            terminal_type="ghostty",
        )

        assert result.success is True
        assert result.run_id == "run-123"
        assert result.child_session_id == "child-456"
        assert result.status == "pending"
        assert result.pid == 12345
        assert result.terminal_type == "ghostty"

    def test_spawn_result_failure(self):
        """Test failed SpawnResult."""
        result = SpawnResult(
            success=False,
            run_id="run-123",
            child_session_id="child-456",
            status="failed",
            error="Failed to spawn process",
        )

        assert result.success is False
        assert result.error == "Failed to spawn process"

    def test_spawn_result_optional_fields(self):
        """Test SpawnResult optional fields have defaults."""
        result = SpawnResult(
            success=True,
            run_id="run",
            child_session_id="child",
            status="pending",
        )

        assert result.pid is None
        assert result.terminal_type is None
        assert result.master_fd is None
        assert result.error is None
        assert result.message is None


class TestExecuteSpawn:
    """Tests for execute_spawn function."""

    @pytest.mark.asyncio
    async def test_terminal_mode_calls_terminal_spawner(self):
        """Test that terminal mode dispatches to TerminalSpawner."""
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="terminal",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            success=True,
            pid=12345,
            terminal_type="ghostty",
            message="Spawned successfully",
        )

        with patch(
            "gobby.agents.spawn_executor.TerminalSpawner",
            return_value=mock_spawner,
        ):
            result = await execute_spawn(request)

            mock_spawner.spawn_agent.assert_called_once()
            assert result.success is True
            assert result.pid == 12345
            assert result.terminal_type == "ghostty"

    @pytest.mark.asyncio
    async def test_embedded_mode_calls_embedded_spawner(self):
        """Test that embedded mode dispatches to EmbeddedSpawner."""
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="embedded",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            success=True,
            pid=12345,
            master_fd=5,
            message="Spawned with PTY",
        )

        with patch(
            "gobby.agents.spawn_executor.EmbeddedSpawner",
            return_value=mock_spawner,
        ):
            result = await execute_spawn(request)

            mock_spawner.spawn_agent.assert_called_once()
            assert result.success is True
            assert result.pid == 12345
            assert result.master_fd == 5

    @pytest.mark.asyncio
    async def test_headless_mode_calls_headless_spawner(self):
        """Test that headless mode dispatches to HeadlessSpawner."""
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="headless",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            success=True,
            pid=12345,
            process=MagicMock(),
            message="Spawned headless",
        )

        with patch(
            "gobby.agents.spawn_executor.HeadlessSpawner",
            return_value=mock_spawner,
        ):
            result = await execute_spawn(request)

            mock_spawner.spawn_agent.assert_called_once()
            assert result.success is True
            assert result.pid == 12345

    @pytest.mark.asyncio
    async def test_spawn_failure_propagates_error(self):
        """Test that spawn failure returns error in result."""
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="terminal",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            success=False,
            error="Terminal not found",
            message="Failed to spawn",
        )

        with patch(
            "gobby.agents.spawn_executor.TerminalSpawner",
            return_value=mock_spawner,
        ):
            result = await execute_spawn(request)

            assert result.success is False
            assert "Terminal not found" in (result.error or result.message or "")

    @pytest.mark.asyncio
    async def test_spawn_passes_workflow_to_spawner(self):
        """Test that workflow is passed to the spawner."""
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="terminal",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
            workflow="auto-task",
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            success=True,
            pid=12345,
            terminal_type="ghostty",
        )

        with patch(
            "gobby.agents.spawn_executor.TerminalSpawner",
            return_value=mock_spawner,
        ):
            await execute_spawn(request)

            call_kwargs = mock_spawner.spawn_agent.call_args
            assert call_kwargs.kwargs.get("workflow_name") == "auto-task"
