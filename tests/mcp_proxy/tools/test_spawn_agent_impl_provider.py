"""
Tests for provider resolution logic in spawn_agent_impl.

Verifies the fix for the dead code bug where `provider or "claude"` short-circuited
the agent_body.provider fallback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.agents.isolation import IsolationContext
from gobby.workflows.definitions import AgentDefinitionBody

pytestmark = pytest.mark.unit


def _make_runner() -> MagicMock:
    runner = MagicMock()
    runner.can_spawn.return_value = (True, "Can spawn", 0)
    runner.child_session_manager = MagicMock()
    runner.run_storage = MagicMock()
    runner.run_storage.has_active_run_for_task.return_value = False
    runner.run_storage.update_child_session = MagicMock()
    runner.run_storage.update_runtime = MagicMock()
    return runner


def _make_execute_spawn_result() -> MagicMock:
    result = MagicMock()
    result.success = True
    result.child_session_id = "child-session-abc"
    result.pid = 12345
    result.terminal_type = "tmux"
    result.tmux_session_name = None
    result.status = "running"
    result.message = None
    result.error = None
    result.process = None
    return result


class TestProviderResolution:
    """Tests for provider resolution in spawn_agent_impl."""

    @pytest.mark.asyncio
    async def test_provider_none_falls_back_to_agent_body_provider(self) -> None:
        """When provider=None, agent_body.provider should be used."""
        from gobby.mcp_proxy.tools.spawn_agent._implementation import spawn_agent_impl

        agent_body = AgentDefinitionBody(
            name="gemini-worker",
            provider="gemini",
            mode="terminal",
        )
        runner = _make_runner()

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_project_context"
            ) as mock_ctx,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_isolation_handler"
            ) as mock_get_handler,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.execute_spawn"
            ) as mock_execute,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_running_agent_registry"
            ) as mock_registry_fn,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_machine_id",
                return_value="machine-1",
            ),
        ):
            mock_ctx.return_value = {
                "id": "proj-abc",
                "project_path": "/repo",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/repo")
            )
            mock_handler.build_context_prompt.return_value = "Do the thing"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = _make_execute_spawn_result()
            mock_registry_fn.return_value = MagicMock()

            result = await spawn_agent_impl(
                prompt="Do the thing",
                runner=runner,
                agent_body=agent_body,
                provider=None,  # explicitly None — should fall back to agent_body.provider
                mode="terminal",
                parent_session_id="parent-session-xyz",
            )

        assert result["success"] is True
        # Verify execute_spawn was called with gemini as the provider
        spawn_request = mock_execute.call_args[0][0]
        assert spawn_request.provider == "gemini"

    @pytest.mark.asyncio
    async def test_explicit_provider_overrides_agent_body(self) -> None:
        """When provider is explicitly set, it overrides agent_body.provider."""
        from gobby.mcp_proxy.tools.spawn_agent._implementation import spawn_agent_impl

        agent_body = AgentDefinitionBody(
            name="gemini-worker",
            provider="gemini",
            mode="terminal",
        )
        runner = _make_runner()

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_project_context"
            ) as mock_ctx,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_isolation_handler"
            ) as mock_get_handler,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.execute_spawn"
            ) as mock_execute,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_running_agent_registry"
            ) as mock_registry_fn,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_machine_id",
                return_value="machine-1",
            ),
        ):
            mock_ctx.return_value = {
                "id": "proj-abc",
                "project_path": "/repo",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/repo")
            )
            mock_handler.build_context_prompt.return_value = "Do the thing"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = _make_execute_spawn_result()
            mock_registry_fn.return_value = MagicMock()

            result = await spawn_agent_impl(
                prompt="Do the thing",
                runner=runner,
                agent_body=agent_body,
                provider="claude",  # explicit override
                mode="terminal",
                parent_session_id="parent-session-xyz",
            )

        assert result["success"] is True
        spawn_request = mock_execute.call_args[0][0]
        assert spawn_request.provider == "claude"

    @pytest.mark.asyncio
    async def test_provider_inherit_falls_back_to_claude(self) -> None:
        """When provider='inherit' and no agent_body, defaults to 'claude'."""
        from gobby.mcp_proxy.tools.spawn_agent._implementation import spawn_agent_impl

        runner = _make_runner()

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_project_context"
            ) as mock_ctx,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_isolation_handler"
            ) as mock_get_handler,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.execute_spawn"
            ) as mock_execute,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_running_agent_registry"
            ) as mock_registry_fn,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_machine_id",
                return_value="machine-1",
            ),
        ):
            mock_ctx.return_value = {
                "id": "proj-abc",
                "project_path": "/repo",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/repo")
            )
            mock_handler.build_context_prompt.return_value = "Do the thing"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = _make_execute_spawn_result()
            mock_registry_fn.return_value = MagicMock()

            result = await spawn_agent_impl(
                prompt="Do the thing",
                runner=runner,
                agent_body=None,
                provider="inherit",
                mode="terminal",
                parent_session_id="parent-session-xyz",
            )

        assert result["success"] is True
        spawn_request = mock_execute.call_args[0][0]
        assert spawn_request.provider == "claude"

    @pytest.mark.asyncio
    async def test_provider_none_no_agent_body_defaults_to_claude(self) -> None:
        """When provider=None and no agent_body, defaults to 'claude'."""
        from gobby.mcp_proxy.tools.spawn_agent._implementation import spawn_agent_impl

        runner = _make_runner()

        with (
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_project_context"
            ) as mock_ctx,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_isolation_handler"
            ) as mock_get_handler,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.execute_spawn"
            ) as mock_execute,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_running_agent_registry"
            ) as mock_registry_fn,
            patch(
                "gobby.mcp_proxy.tools.spawn_agent._implementation.get_machine_id",
                return_value="machine-1",
            ),
        ):
            mock_ctx.return_value = {
                "id": "proj-abc",
                "project_path": "/repo",
            }
            mock_handler = MagicMock()
            mock_handler.prepare_environment = AsyncMock(
                return_value=IsolationContext(cwd="/repo")
            )
            mock_handler.build_context_prompt.return_value = "Do the thing"
            mock_get_handler.return_value = mock_handler

            mock_execute.return_value = _make_execute_spawn_result()
            mock_registry_fn.return_value = MagicMock()

            result = await spawn_agent_impl(
                prompt="Do the thing",
                runner=runner,
                agent_body=None,
                provider=None,
                mode="terminal",
                parent_session_id="parent-session-xyz",
            )

        assert result["success"] is True
        spawn_request = mock_execute.call_args[0][0]
        assert spawn_request.provider == "claude"
