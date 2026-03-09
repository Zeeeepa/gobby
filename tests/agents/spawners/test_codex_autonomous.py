"""Tests for CodexAutonomousRunner — Codex-based autonomous agent execution.

Covers:
- Successful run with mocked CodexAppServerClient
- Thread ID capture
- Agent run manager integration (complete/fail calls)
- Error handling (CLI not found, client error, cancellation)
- Auto-approve behavior via approval handler
- Context injection (system prompt, env context)
- Lifecycle callbacks (before_agent, pre_tool, post_tool)
- Resume support via thread_id
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.adapters.codex_impl.types import CodexThread, CodexTurn
from gobby.agents.spawners.codex_autonomous import CodexAutonomousRunner

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner(**overrides: Any) -> CodexAutonomousRunner:
    """Create a CodexAutonomousRunner with sensible test defaults."""
    defaults = {
        "session_id": "test-session-123",
        "run_id": "test-run-456",
        "project_id": "test-project",
        "cwd": "/tmp/test-workspace",
        "prompt": "Fix the bug in main.py",
        "model": "gpt-4.1",
        "system_prompt": "You are a test agent.",
        "max_turns": 5,
        "seq_num": 42,
    }
    defaults.update(overrides)
    return CodexAutonomousRunner(**defaults)


def _mock_client(thread_id: str = "thread-abc-123") -> AsyncMock:
    """Create a mock CodexAppServerClient."""
    client = AsyncMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.register_approval_handler = MagicMock()
    client.add_notification_handler = MagicMock()
    client.remove_notification_handler = MagicMock()

    thread = CodexThread(id=thread_id, preview="test", model_provider="openai")
    client.start_thread = AsyncMock(return_value=thread)
    client.resume_thread = AsyncMock(return_value=thread)

    turn = CodexTurn(id="turn-1", thread_id=thread_id, status="inProgress")
    client.start_turn = AsyncMock(return_value=turn)

    return client


def _simulate_turn(client: AsyncMock, text: str = "Done!") -> None:
    """Set up notification handlers to simulate a turn with text output.

    Captures handlers registered via add_notification_handler and calls
    them to simulate delta events and turn completion.
    """
    handlers: dict[str, Any] = {}

    def _capture_handler(method: str, handler: Any) -> None:
        handlers[method] = handler

    client.add_notification_handler.side_effect = _capture_handler

    original_start_turn = client.start_turn

    async def _start_turn_with_events(*args: Any, **kwargs: Any) -> Any:
        result = await original_start_turn(*args, **kwargs)
        # Simulate delta events
        if "item/agentMessage/delta" in handlers:
            handlers["item/agentMessage/delta"](
                "item/agentMessage/delta", {"delta": text}
            )
        # Simulate turn completion
        if "turn/completed" in handlers:
            handlers["turn/completed"]("turn/completed", {})
        return result

    client.start_turn = AsyncMock(side_effect=_start_turn_with_events)


# ---------------------------------------------------------------------------
# Successful run
# ---------------------------------------------------------------------------


class TestSuccessfulRun:
    @pytest.mark.asyncio
    async def test_basic_run_returns_text(self) -> None:
        """Runner accumulates text from delta events."""
        client = _mock_client()
        _simulate_turn(client, text="Working on it... Done!")
        runner = _make_runner()

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            result = await runner.run()

        assert "Working on it... Done!" in result
        client.start.assert_awaited_once()
        client.start_thread.assert_awaited_once()
        client.start_turn.assert_awaited_once()
        client.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_turn_returns_empty_string(self) -> None:
        """Turn with no delta events returns empty string."""
        client = _mock_client()
        _simulate_turn(client, text="")
        runner = _make_runner()

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            result = await runner.run()

        assert result == ""


# ---------------------------------------------------------------------------
# Thread ID capture
# ---------------------------------------------------------------------------


class TestThreadIdCapture:
    @pytest.mark.asyncio
    async def test_captures_thread_id(self) -> None:
        """thread_id is set from the started thread."""
        client = _mock_client(thread_id="captured-thread-xyz")
        _simulate_turn(client, text="ok")
        runner = _make_runner()

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        assert runner.thread_id == "captured-thread-xyz"


# ---------------------------------------------------------------------------
# Agent run manager
# ---------------------------------------------------------------------------


class TestAgentRunManager:
    @pytest.mark.asyncio
    async def test_complete_called_on_success(self) -> None:
        """Agent run manager complete() is called with result."""
        manager = MagicMock()
        client = _mock_client()
        _simulate_turn(client, text="Result text")
        runner = _make_runner(agent_run_manager=manager)

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        manager.complete.assert_called_once()
        call_args = manager.complete.call_args
        assert call_args[0][0] == "test-run-456"
        assert "Result text" in call_args[1]["result"]

    @pytest.mark.asyncio
    async def test_update_sdk_session_id_called(self) -> None:
        """Agent run manager receives thread_id for cross-mode resume."""
        manager = MagicMock()
        client = _mock_client(thread_id="thread-for-resume")
        _simulate_turn(client, text="ok")
        runner = _make_runner(agent_run_manager=manager)

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        manager.update_sdk_session_id.assert_called_once_with(
            "test-run-456", "thread-for-resume"
        )

    @pytest.mark.asyncio
    async def test_fail_called_on_error(self) -> None:
        """Agent run manager fail() is called on exception."""
        manager = MagicMock()
        client = _mock_client()
        client.start = AsyncMock(side_effect=RuntimeError("Connection failed"))
        runner = _make_runner(agent_run_manager=manager)

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            with pytest.raises(RuntimeError, match="Connection failed"):
                await runner.run()

        manager.fail.assert_called_once()
        assert "Connection failed" in manager.fail.call_args[1]["error"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_codex_not_available(self) -> None:
        """Raises RuntimeError when Codex CLI is not found."""
        runner = _make_runner()

        with patch(
            "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="Codex CLI not found"):
                await runner.run()

    @pytest.mark.asyncio
    async def test_cancellation_calls_fail(self) -> None:
        """CancelledError calls agent_run_manager.fail() with 'Cancelled'."""
        manager = MagicMock()
        client = _mock_client()

        # Make start_turn hang forever (simulates an in-progress turn)
        client.start_turn = AsyncMock(side_effect=asyncio.CancelledError())
        runner = _make_runner(agent_run_manager=manager)

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            with pytest.raises(asyncio.CancelledError):
                await runner.run()

        manager.fail.assert_called_once()
        assert "Cancelled" in manager.fail.call_args[1]["error"]

    @pytest.mark.asyncio
    async def test_client_stopped_on_error(self) -> None:
        """Client.stop() is called even when an error occurs."""
        client = _mock_client()
        client.start_thread = AsyncMock(side_effect=RuntimeError("thread error"))
        runner = _make_runner()

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            with pytest.raises(RuntimeError):
                await runner.run()

        client.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# Auto-approve
# ---------------------------------------------------------------------------


class TestAutoApprove:
    @pytest.mark.asyncio
    async def test_approval_policy_is_never(self) -> None:
        """start_thread is called with approval_policy='never'."""
        client = _mock_client()
        _simulate_turn(client, text="ok")
        runner = _make_runner()

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        call_kwargs = client.start_thread.call_args[1]
        assert call_kwargs["approval_policy"] == "never"

    @pytest.mark.asyncio
    async def test_approval_handler_registered(self) -> None:
        """An approval handler is registered on the client."""
        client = _mock_client()
        _simulate_turn(client, text="ok")
        runner = _make_runner()

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        client.register_approval_handler.assert_called_once()


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------


class TestContextInjection:
    @pytest.mark.asyncio
    async def test_system_prompt_in_context_prefix(self) -> None:
        """System prompt is included in the context_prefix."""
        client = _mock_client()
        _simulate_turn(client, text="ok")
        runner = _make_runner(system_prompt="Custom system prompt.")

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        call_kwargs = client.start_turn.call_args[1]
        assert "Custom system prompt." in call_kwargs["context_prefix"]

    @pytest.mark.asyncio
    async def test_session_ref_in_context_prefix(self) -> None:
        """Session ref (#seq_num) is included in context_prefix."""
        client = _mock_client()
        _simulate_turn(client, text="ok")
        runner = _make_runner(seq_num=99)

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        call_kwargs = client.start_turn.call_args[1]
        assert "#99" in call_kwargs["context_prefix"]


# ---------------------------------------------------------------------------
# Lifecycle callbacks
# ---------------------------------------------------------------------------


class TestLifecycleCallbacks:
    @pytest.mark.asyncio
    async def test_before_agent_callback_fired(self) -> None:
        """on_before_agent callback is invoked before turn start."""
        before_agent = AsyncMock(return_value={"context": "Extra context"})
        client = _mock_client()
        _simulate_turn(client, text="ok")
        runner = _make_runner(on_before_agent=before_agent)

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        before_agent.assert_awaited_once()
        data = before_agent.call_args[0][0]
        assert data["prompt"] == "Fix the bug in main.py"
        assert data["source"] == "codex_autonomous"

        # Context should be merged into context_prefix
        call_kwargs = client.start_turn.call_args[1]
        assert "Extra context" in call_kwargs["context_prefix"]


# ---------------------------------------------------------------------------
# Resume support
# ---------------------------------------------------------------------------


class TestResumeSupport:
    @pytest.mark.asyncio
    async def test_resume_uses_resume_thread(self) -> None:
        """When resume_session_id is set, resume_thread is used."""
        client = _mock_client()
        _simulate_turn(client, text="resumed")
        runner = _make_runner(resume_session_id="existing-thread-id")

        with (
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAdapter.is_codex_available",
                return_value=True,
            ),
            patch(
                "gobby.agents.spawners.codex_autonomous.CodexAppServerClient",
                return_value=client,
            ),
        ):
            await runner.run()

        client.resume_thread.assert_awaited_once_with("existing-thread-id")
        client.start_thread.assert_not_awaited()
