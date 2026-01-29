"""
Tests for SpawnExecutor unified spawn dispatch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.sandbox import SandboxConfig
from gobby.agents.spawn_executor import (
    SpawnRequest,
    SpawnResult,
    execute_spawn,
)

pytestmark = pytest.mark.unit


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

    def test_spawn_request_sandbox_fields_default_to_none(self) -> None:
        """Test SpawnRequest sandbox fields default to None."""
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

        assert request.sandbox_config is None
        assert request.sandbox_args is None
        assert request.sandbox_env is None

    def test_spawn_request_accepts_sandbox_fields(self) -> None:
        """Test SpawnRequest accepts sandbox configuration."""
        sandbox_config = SandboxConfig(enabled=True, mode="restrictive")
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
            sandbox_config=sandbox_config,
            sandbox_args=["--settings", '{"sandbox":{"enabled":true}}'],
            sandbox_env={"SEATBELT_PROFILE": "restrictive-closed"},
        )

        assert request.sandbox_config is not None
        assert request.sandbox_config.enabled is True
        assert request.sandbox_config.mode == "restrictive"
        assert request.sandbox_args == ["--settings", '{"sandbox":{"enabled":true}}']
        assert request.sandbox_env == {"SEATBELT_PROFILE": "restrictive-closed"}


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

    @pytest.mark.asyncio
    async def test_gemini_terminal_spawns_without_preflight(self):
        """Test that provider='gemini' with mode='terminal' spawns directly without preflight.

        Session registration is handled by Gemini's startup hook, not pre-creation.
        """
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="terminal",
            provider="gemini",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn.return_value = MagicMock(
            success=True,
            pid=12345,
        )

        with (
            patch(
                "gobby.agents.spawn_executor.build_cli_command",
                return_value=["gemini", "."],
            ),
            patch(
                "gobby.agents.spawn_executor.TerminalSpawner",
                return_value=mock_spawner,
            ),
        ):
            result = await execute_spawn(request)

            # Verify spawn was called without env vars (no pre-created session)
            mock_spawner.spawn.assert_called_once()
            call_kwargs = mock_spawner.spawn.call_args.kwargs
            assert "env" not in call_kwargs or call_kwargs.get("env") is None
            assert result.success is True
            # child_session_id is None because startup hook will register it
            assert result.child_session_id is None
            assert result.pid == 12345

    @pytest.mark.asyncio
    async def test_codex_terminal_calls_preflight(self):
        """Test that provider='codex' with mode='terminal' calls prepare_codex_spawn_with_preflight."""
        mock_session_manager = MagicMock()
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="terminal",
            provider="codex",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
            session_manager=mock_session_manager,
        )

        mock_preflight = AsyncMock(
            return_value=MagicMock(
                session_id="gobby-sess-123",
                env_vars={"GOBBY_CODEX_EXTERNAL_ID": "codex-ext-789"},
            )
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn.return_value = MagicMock(
            success=True,
            pid=12345,
        )

        with (
            patch(
                "gobby.agents.spawn_executor.prepare_codex_spawn_with_preflight",
                mock_preflight,
            ),
            patch(
                "gobby.agents.spawn_executor.build_codex_command_with_resume",
                return_value=["codex", "--resume"],
            ),
            patch(
                "gobby.agents.spawn_executor.TerminalSpawner",
                return_value=mock_spawner,
            ),
        ):
            result = await execute_spawn(request)

            mock_preflight.assert_called_once()
            assert result.success is True
            assert result.codex_session_id == "codex-ext-789"

    @pytest.mark.asyncio
    async def test_gemini_terminal_spawn_failure_propagates_error(self):
        """Test that Gemini spawn failure is properly propagated to SpawnResult."""
        request = SpawnRequest(
            prompt="Test",
            cwd="/path",
            mode="terminal",
            provider="gemini",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn.return_value = MagicMock(
            success=False,
            error="Terminal not found",
            message=None,
        )

        with (
            patch(
                "gobby.agents.spawn_executor.build_cli_command",
                return_value=["gemini", "."],
            ),
            patch(
                "gobby.agents.spawn_executor.TerminalSpawner",
                return_value=mock_spawner,
            ),
        ):
            result = await execute_spawn(request)

            assert result.success is False
            assert "Terminal not found" in (result.error or "")


class TestExecuteSpawnSandbox:
    """Integration tests for sandbox configuration in spawn flow."""

    @pytest.mark.asyncio
    async def test_terminal_spawn_passes_sandbox_config_to_spawner(self) -> None:
        """Test that sandbox_config is passed to TerminalSpawner."""
        sandbox_config = SandboxConfig(enabled=True, mode="permissive")
        request = SpawnRequest(
            prompt="Test with sandbox",
            cwd="/path",
            mode="terminal",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
            sandbox_config=sandbox_config,
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
            result = await execute_spawn(request)

            # Verify sandbox_config was passed to spawn_agent
            mock_spawner.spawn_agent.assert_called_once()
            call_kwargs = mock_spawner.spawn_agent.call_args.kwargs
            assert "sandbox_config" in call_kwargs
            assert call_kwargs["sandbox_config"].enabled is True
            assert call_kwargs["sandbox_config"].mode == "permissive"
            assert result.success is True

    @pytest.mark.asyncio
    async def test_terminal_spawn_without_sandbox_passes_none(self) -> None:
        """Test that spawn without sandbox passes sandbox_config=None."""
        request = SpawnRequest(
            prompt="Test without sandbox",
            cwd="/path",
            mode="terminal",
            provider="claude",
            terminal="auto",
            session_id="sess",
            run_id="run",
            parent_session_id="parent",
            project_id="proj",
            # No sandbox_config specified
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
            result = await execute_spawn(request)

            mock_spawner.spawn_agent.assert_called_once()
            call_kwargs = mock_spawner.spawn_agent.call_args.kwargs
            # sandbox_config should be None or not present
            assert call_kwargs.get("sandbox_config") is None
            assert result.success is True

    @pytest.mark.asyncio
    async def test_embedded_spawn_passes_sandbox_config(self) -> None:
        """Test that sandbox_config is passed to EmbeddedSpawner."""
        sandbox_config = SandboxConfig(enabled=True, mode="restrictive")
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
            sandbox_config=sandbox_config,
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            success=True,
            pid=12345,
            master_fd=5,
        )

        with patch(
            "gobby.agents.spawn_executor.EmbeddedSpawner",
            return_value=mock_spawner,
        ):
            result = await execute_spawn(request)

            mock_spawner.spawn_agent.assert_called_once()
            call_kwargs = mock_spawner.spawn_agent.call_args.kwargs
            assert "sandbox_config" in call_kwargs
            assert call_kwargs["sandbox_config"].enabled is True
            assert call_kwargs["sandbox_config"].mode == "restrictive"
            assert result.success is True

    @pytest.mark.asyncio
    async def test_headless_spawn_passes_sandbox_config(self) -> None:
        """Test that sandbox_config is passed to HeadlessSpawner."""
        sandbox_config = SandboxConfig(
            enabled=True,
            mode="permissive",
            allow_network=False,
        )
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
            sandbox_config=sandbox_config,
        )

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            success=True,
            pid=12345,
            process=MagicMock(),
        )

        with patch(
            "gobby.agents.spawn_executor.HeadlessSpawner",
            return_value=mock_spawner,
        ):
            result = await execute_spawn(request)

            mock_spawner.spawn_agent.assert_called_once()
            call_kwargs = mock_spawner.spawn_agent.call_args.kwargs
            assert "sandbox_config" in call_kwargs
            assert call_kwargs["sandbox_config"].enabled is True
            assert call_kwargs["sandbox_config"].allow_network is False
            assert result.success is True

    @pytest.mark.asyncio
    async def test_sandbox_disabled_explicitly_passed(self) -> None:
        """Test that explicitly disabled sandbox is passed correctly."""
        sandbox_config = SandboxConfig(enabled=False)
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
            sandbox_config=sandbox_config,
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
            result = await execute_spawn(request)

            mock_spawner.spawn_agent.assert_called_once()
            call_kwargs = mock_spawner.spawn_agent.call_args.kwargs
            assert "sandbox_config" in call_kwargs
            assert call_kwargs["sandbox_config"].enabled is False
            assert result.success is True
