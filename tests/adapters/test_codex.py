"""Comprehensive tests for Codex CLI adapter.

Tests cover:
1. CodexAppServerClient - subprocess and JSON-RPC management
2. CodexAdapter - event translation from app-server
3. CodexNotifyAdapter - notify hook handling
4. Data types and utilities
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.adapters.codex_impl.adapter import (
    CodexAdapter,
    CodexNotifyAdapter,
    _get_daemon_machine_id,
)
from gobby.adapters.codex_impl.client import CodexAppServerClient
from gobby.adapters.codex_impl.types import (
    CodexConnectionState,
    CodexItem,
    CodexThread,
    CodexTurn,
)
from gobby.hooks.events import HookEventType, HookResponse, SessionSource

pytestmark = pytest.mark.unit

# =============================================================================
# Data Types Tests
# =============================================================================


class TestCodexConnectionState:
    """Tests for CodexConnectionState enum."""

    def test_connection_states(self) -> None:
        """All connection states are defined."""
        assert CodexConnectionState.DISCONNECTED.value == "disconnected"
        assert CodexConnectionState.CONNECTING.value == "connecting"
        assert CodexConnectionState.CONNECTED.value == "connected"
        assert CodexConnectionState.ERROR.value == "error"


class TestCodexThread:
    """Tests for CodexThread dataclass."""

    def test_create_minimal(self) -> None:
        """Create thread with only required field."""
        thread = CodexThread(id="thr-123")

        assert thread.id == "thr-123"
        assert thread.preview == ""
        assert thread.model_provider == "openai"
        assert thread.created_at == 0

    def test_create_full(self) -> None:
        """Create thread with all fields."""
        thread = CodexThread(
            id="thr-456",
            preview="Help me refactor",
            model_provider="anthropic",
            created_at=1704067200,
        )

        assert thread.id == "thr-456"
        assert thread.preview == "Help me refactor"
        assert thread.model_provider == "anthropic"
        assert thread.created_at == 1704067200


class TestCodexTurn:
    """Tests for CodexTurn dataclass."""

    def test_create_minimal(self) -> None:
        """Create turn with required fields."""
        turn = CodexTurn(id="turn-1", thread_id="thr-1")

        assert turn.id == "turn-1"
        assert turn.thread_id == "thr-1"
        assert turn.status == "pending"
        assert turn.items == []
        assert turn.error is None
        assert turn.usage is None

    def test_create_full(self) -> None:
        """Create turn with all fields."""
        turn = CodexTurn(
            id="turn-2",
            thread_id="thr-2",
            status="completed",
            items=[{"type": "message", "text": "Done"}],
            error="Some error",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        assert turn.status == "completed"
        assert len(turn.items) == 1
        assert turn.error == "Some error"
        assert turn.usage["input_tokens"] == 100


class TestCodexItem:
    """Tests for CodexItem dataclass."""

    def test_create_minimal(self) -> None:
        """Create item with required fields."""
        item = CodexItem(id="item-1", type="reasoning")

        assert item.id == "item-1"
        assert item.type == "reasoning"
        assert item.content == ""
        assert item.status == "pending"
        assert item.metadata == {}

    def test_create_full(self) -> None:
        """Create item with all fields."""
        item = CodexItem(
            id="item-2",
            type="agent_message",
            content="I'll help you with that",
            status="completed",
            metadata={"model": "gpt-4"},
        )

        assert item.content == "I'll help you with that"
        assert item.status == "completed"
        assert item.metadata["model"] == "gpt-4"


class TestGetMachineId:
    """Tests for _get_daemon_machine_id utility."""

    def test_returns_string(self) -> None:
        """Returns a string machine ID."""
        machine_id = _get_daemon_machine_id()
        assert isinstance(machine_id, str)
        assert len(machine_id) > 0

    @patch("gobby.utils.machine_id.get_machine_id")
    def test_returns_stable_id(self, mock_get_machine_id) -> None:
        """Returns stable ID from utils.machine_id."""
        mock_get_machine_id.return_value = "test-machine-id-12345"

        id1 = _get_daemon_machine_id()
        id2 = _get_daemon_machine_id()

        # Same machine should produce same ID
        assert id1 == id2
        assert id1 == "test-machine-id-12345"

    @patch("gobby.utils.machine_id.get_machine_id")
    def test_fallback_when_no_hostname(self, mock_get_machine_id) -> None:
        """Returns valid ID from utils.machine_id (may be UUID or machineid format)."""
        # machineid returns 32-char hex, uuid4 returns 36-char UUID
        mock_get_machine_id.return_value = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"

        machine_id = _get_daemon_machine_id()
        assert isinstance(machine_id, str)
        # Accept both machineid format (32 chars) and UUID format (36 chars)
        assert len(machine_id) >= 32


# =============================================================================
# CodexAppServerClient Tests
# =============================================================================


class TestCodexAppServerClientInit:
    """Tests for CodexAppServerClient initialization."""

    def test_default_init(self) -> None:
        """Default initialization."""
        client = CodexAppServerClient()

        assert client._codex_command == "codex"
        assert client._on_notification is None
        assert client._process is None
        assert client.state == CodexConnectionState.DISCONNECTED
        assert client.is_connected is False

    def test_custom_command(self) -> None:
        """Initialize with custom codex command."""
        client = CodexAppServerClient(codex_command="/custom/codex")
        assert client._codex_command == "/custom/codex"

    def test_with_notification_handler(self) -> None:
        """Initialize with notification handler."""

        def handler(method: str, params: dict) -> None:
            pass

        client = CodexAppServerClient(on_notification=handler)
        assert client._on_notification is handler


class TestCodexAppServerClientProperties:
    """Tests for CodexAppServerClient properties."""

    def test_state_property(self) -> None:
        """State property returns current state."""
        client = CodexAppServerClient()
        assert client.state == CodexConnectionState.DISCONNECTED

    def test_is_connected_false_when_disconnected(self) -> None:
        """is_connected returns False when disconnected."""
        client = CodexAppServerClient()
        assert client.is_connected is False

    def test_is_connected_true_when_connected(self) -> None:
        """is_connected returns True when connected."""
        client = CodexAppServerClient()
        client._state = CodexConnectionState.CONNECTED
        assert client.is_connected is True


class TestCodexAppServerClientNotificationHandlers:
    """Tests for notification handler management."""

    def test_add_notification_handler(self) -> None:
        """Add a notification handler."""
        client = CodexAppServerClient()
        handler = MagicMock()

        client.add_notification_handler("turn/started", handler)

        assert "turn/started" in client._notification_handlers
        assert handler in client._notification_handlers["turn/started"]

    def test_add_multiple_handlers(self) -> None:
        """Add multiple handlers for same method."""
        client = CodexAppServerClient()
        handler1 = MagicMock()
        handler2 = MagicMock()

        client.add_notification_handler("turn/completed", handler1)
        client.add_notification_handler("turn/completed", handler2)

        assert len(client._notification_handlers["turn/completed"]) == 2

    def test_remove_notification_handler(self) -> None:
        """Remove a notification handler."""
        client = CodexAppServerClient()
        handler = MagicMock()

        client.add_notification_handler("item/completed", handler)
        client.remove_notification_handler("item/completed", handler)

        assert handler not in client._notification_handlers.get("item/completed", [])

    def test_remove_nonexistent_handler(self) -> None:
        """Remove handler that doesn't exist."""
        client = CodexAppServerClient()
        handler = MagicMock()

        # Should not raise
        client.remove_notification_handler("missing", handler)


class TestCodexAppServerClientStart:
    """Tests for CodexAppServerClient.start()."""

    @pytest.mark.asyncio
    async def test_start_spawns_subprocess(self):
        """Start spawns codex app-server subprocess."""
        client = CodexAppServerClient()

        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.poll.return_value = None

        # Mock the response for initialize request
        def mock_readline():
            return (
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex/1.0"}}) + "\n"
            )

        mock_process.stdout.readline = mock_readline

        with patch(
            "gobby.adapters.codex_impl.client.subprocess.Popen", return_value=mock_process
        ) as mock_popen:
            # Create a task that will complete quickly
            async def run_start():
                try:
                    await asyncio.wait_for(client.start(), timeout=0.5)
                except TimeoutError:
                    pass

            await run_start()

            mock_popen.assert_called_once()
            args = mock_popen.call_args
            assert args[0][0] == ["codex", "app-server"]

        await client.stop()

    @pytest.mark.asyncio
    async def test_start_when_already_connected(self):
        """Start returns early when already connected."""
        client = CodexAppServerClient()
        client._state = CodexConnectionState.CONNECTED

        await client.start()

        # State should remain connected
        assert client.state == CodexConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_start_failure_sets_error_state(self):
        """Start sets error state on failure."""
        client = CodexAppServerClient()

        with patch(
            "gobby.adapters.codex_impl.client.subprocess.Popen",
            side_effect=OSError("Command not found"),
        ):
            with pytest.raises(RuntimeError, match="Failed to start"):
                await client.start()

        assert client.state == CodexConnectionState.DISCONNECTED


class TestCodexAppServerClientStop:
    """Tests for CodexAppServerClient.stop()."""

    @pytest.mark.asyncio
    async def test_stop_terminates_process(self):
        """Stop terminates the subprocess."""
        client = CodexAppServerClient()

        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.wait.return_value = 0
        client._process = mock_process

        await client.stop()

        mock_process.terminate.assert_called_once()
        assert client._process is None
        assert client.state == CodexConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_stop_cancels_reader_task(self):
        """Stop cancels the reader task."""
        client = CodexAppServerClient()

        # Create an actual asyncio task that we can cancel
        async def long_running():
            await asyncio.sleep(100)

        mock_task = asyncio.create_task(long_running())
        client._reader_task = mock_task

        # Mock the process
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.wait.return_value = 0
        client._process = mock_process

        await client.stop()

        assert mock_task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_cancels_pending_requests(self):
        """Stop cancels all pending requests."""
        client = CodexAppServerClient()

        future1 = asyncio.get_event_loop().create_future()
        future2 = asyncio.get_event_loop().create_future()
        client._pending_requests = {1: future1, 2: future2}

        await client.stop()

        assert future1.cancelled()
        assert future2.cancelled()
        assert client._pending_requests == {}


class TestCodexAppServerClientContextManager:
    """Tests for async context manager support."""

    @pytest.mark.asyncio
    async def test_context_manager_start_stop(self):
        """Context manager starts and stops client."""
        client = CodexAppServerClient()

        with patch.object(client, "start", new_callable=AsyncMock) as mock_start:
            with patch.object(client, "stop", new_callable=AsyncMock) as mock_stop:
                async with client:
                    mock_start.assert_called_once()

                mock_stop.assert_called_once()


class TestCodexAppServerClientRequestId:
    """Tests for request ID generation."""

    def test_next_request_id_increments(self) -> None:
        """Request ID increments with each call."""
        client = CodexAppServerClient()

        id1 = client._next_request_id()
        id2 = client._next_request_id()
        id3 = client._next_request_id()

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3


class TestCodexAppServerClientSendRequest:
    """Tests for _send_request method."""

    @pytest.mark.asyncio
    async def test_send_request_not_connected(self):
        """send_request raises when not connected."""
        client = CodexAppServerClient()

        with pytest.raises(RuntimeError, match="Not connected"):
            await client._send_request("test", {})

    @pytest.mark.asyncio
    async def test_send_request_formats_jsonrpc(self):
        """send_request sends properly formatted JSON-RPC."""
        client = CodexAppServerClient()

        mock_stdin = MagicMock()
        written_lines = []
        mock_stdin.write = lambda x: written_lines.append(x)
        mock_stdin.flush = MagicMock()

        mock_process = MagicMock()
        mock_process.stdin = mock_stdin
        client._process = mock_process

        # Create a future that we'll resolve
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        future.set_result({"key": "value"})

        with patch.dict(client._pending_requests, {1: future}):
            # This should timeout but we want to check the written data
            try:
                await asyncio.wait_for(
                    client._send_request("test/method", {"arg": "val"}), timeout=0.1
                )
            except TimeoutError:
                pass  # Expected - we're testing request was written before timeout

        assert len(written_lines) > 0
        message = json.loads(written_lines[0].strip())
        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "test/method"
        assert message["params"] == {"arg": "val"}
        assert "id" in message


class TestCodexAppServerClientSendNotification:
    """Tests for _send_notification method."""

    @pytest.mark.asyncio
    async def test_send_notification_not_connected(self):
        """send_notification raises when not connected."""
        client = CodexAppServerClient()

        with pytest.raises(RuntimeError, match="Not connected"):
            await client._send_notification("test", {})

    @pytest.mark.asyncio
    async def test_send_notification_formats_message(self):
        """send_notification sends proper notification format (no id)."""
        client = CodexAppServerClient()

        mock_stdin = MagicMock()
        written_lines = []
        mock_stdin.write = lambda x: written_lines.append(x)
        mock_stdin.flush = MagicMock()

        mock_process = MagicMock()
        mock_process.stdin = mock_stdin
        client._process = mock_process

        await client._send_notification("initialized", {})

        assert len(written_lines) == 1
        message = json.loads(written_lines[0].strip())
        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "initialized"
        assert "id" not in message


class TestCodexAppServerClientThreadManagement:
    """Tests for thread management methods."""

    @pytest.mark.asyncio
    async def test_start_thread(self):
        """start_thread sends request and returns thread."""
        client = CodexAppServerClient()

        mock_result = {
            "thread": {
                "id": "thr-new",
                "preview": "",
                "modelProvider": "openai",
                "createdAt": 1704067200,
            }
        }

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            thread = await client.start_thread(cwd="/project", model="gpt-4")

            mock_send.assert_called_once_with(
                "thread/start",
                {"cwd": "/project", "model": "gpt-4"},
            )

        assert thread.id == "thr-new"
        assert thread.model_provider == "openai"
        assert "thr-new" in client._threads

    @pytest.mark.asyncio
    async def test_resume_thread(self):
        """resume_thread sends request and returns thread."""
        client = CodexAppServerClient()

        mock_result = {
            "thread": {
                "id": "thr-existing",
                "preview": "Previous work",
                "modelProvider": "anthropic",
                "createdAt": 1704000000,
            }
        }

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ):
            thread = await client.resume_thread("thr-existing")

        assert thread.id == "thr-existing"
        assert thread.preview == "Previous work"
        assert "thr-existing" in client._threads

    @pytest.mark.asyncio
    async def test_list_threads(self):
        """list_threads returns paginated thread list."""
        client = CodexAppServerClient()

        mock_result = {
            "data": [
                {"id": "thr-1", "preview": "First", "modelProvider": "openai", "createdAt": 1000},
                {"id": "thr-2", "preview": "Second", "modelProvider": "openai", "createdAt": 2000},
            ],
            "nextCursor": "cursor-abc",
        }

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            threads, cursor = await client.list_threads(cursor=None, limit=10)

            mock_send.assert_called_once_with("thread/list", {"limit": 10})

        assert len(threads) == 2
        assert threads[0].id == "thr-1"
        assert cursor == "cursor-abc"

    @pytest.mark.asyncio
    async def test_archive_thread(self):
        """archive_thread sends request and removes from cache."""
        client = CodexAppServerClient()
        client._threads["thr-delete"] = CodexThread(id="thr-delete")

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value={}
        ) as mock_send:
            await client.archive_thread("thr-delete")

            mock_send.assert_called_once_with("thread/archive", {"threadId": "thr-delete"})

        assert "thr-delete" not in client._threads


class TestCodexAppServerClientTurnManagement:
    """Tests for turn management methods."""

    @pytest.mark.asyncio
    async def test_start_turn(self):
        """start_turn sends request and returns turn."""
        client = CodexAppServerClient()

        mock_result = {
            "turn": {
                "id": "turn-new",
                "status": "inProgress",
                "items": [],
            }
        }

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            turn = await client.start_turn("thr-1", "Help me refactor")

            call_args = mock_send.call_args
            assert call_args[0][0] == "turn/start"
            params = call_args[0][1]
            assert params["threadId"] == "thr-1"
            assert params["input"][0]["type"] == "text"
            assert params["input"][0]["text"] == "Help me refactor"

        assert turn.id == "turn-new"
        assert turn.thread_id == "thr-1"
        assert turn.status == "inProgress"

    @pytest.mark.asyncio
    async def test_start_turn_with_images(self):
        """start_turn handles image inputs."""
        client = CodexAppServerClient()

        mock_result = {"turn": {"id": "turn-img", "status": "inProgress", "items": []}}

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            await client.start_turn(
                "thr-1",
                "What's in this image?",
                images=["https://example.com/img.png", "/local/path.jpg"],
            )

            params = mock_send.call_args[0][1]
            assert len(params["input"]) == 3
            assert params["input"][1]["type"] == "image"
            assert params["input"][1]["url"] == "https://example.com/img.png"
            assert params["input"][2]["type"] == "localImage"
            assert params["input"][2]["path"] == "/local/path.jpg"

    @pytest.mark.asyncio
    async def test_interrupt_turn(self):
        """interrupt_turn sends request."""
        client = CodexAppServerClient()

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value={}
        ) as mock_send:
            await client.interrupt_turn("thr-1", "turn-1")

            mock_send.assert_called_once_with(
                "turn/interrupt",
                {"threadId": "thr-1", "turnId": "turn-1"},
            )


class TestCodexAppServerClientRunTurn:
    """Tests for run_turn streaming method."""

    @pytest.mark.asyncio
    async def test_run_turn_yields_events(self):
        """run_turn yields streaming events."""
        client = CodexAppServerClient()

        mock_result = {"turn": {"id": "turn-stream", "status": "inProgress", "items": []}}

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ):
            events = []
            # Simulate notification that ends the turn
            client._notification_handlers["turn/completed"] = []

            async def collect_events():
                async for event in client.run_turn("thr-1", "Test"):
                    events.append(event)
                    if event["type"] == "turn/created":
                        # Simulate completion
                        for handler in client._notification_handlers.get("turn/completed", []):
                            handler(
                                "turn/completed",
                                {"turn": {"id": "turn-stream", "status": "completed"}},
                            )
                        break

            await collect_events()

            assert len(events) >= 1
            assert events[0]["type"] == "turn/created"


class TestCodexAppServerClientAuthentication:
    """Tests for authentication methods."""

    @pytest.mark.asyncio
    async def test_login_with_api_key(self):
        """login_with_api_key sends request."""
        client = CodexAppServerClient()

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value={"success": True}
        ) as mock_send:
            result = await client.login_with_api_key("sk-test-key")

            mock_send.assert_called_once_with(
                "account/login/start",
                {"type": "apiKey", "apiKey": "sk-test-key"},
            )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_account_status(self):
        """get_account_status sends request."""
        client = CodexAppServerClient()

        mock_status = {"authenticated": True, "user": "test@example.com"}

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_status
        ) as mock_send:
            result = await client.get_account_status()

            mock_send.assert_called_once_with("account/status", {})

        assert result["authenticated"] is True


# =============================================================================
# CodexAdapter Tests
# =============================================================================


class TestCodexAdapterInit:
    """Tests for CodexAdapter initialization."""

    def test_default_init(self) -> None:
        """Default initialization."""
        adapter = CodexAdapter()

        assert adapter._hook_manager is None
        assert adapter._codex_client is None
        assert adapter._machine_id is None
        assert adapter._attached is False
        assert adapter.source == SessionSource.CODEX

    def test_with_hook_manager(self) -> None:
        """Initialize with hook manager."""
        mock_hook_manager = MagicMock()
        adapter = CodexAdapter(hook_manager=mock_hook_manager)

        assert adapter._hook_manager is mock_hook_manager


class TestCodexAdapterIsAvailable:
    """Tests for is_codex_available static method."""

    @patch("shutil.which")
    def test_codex_available(self, mock_which) -> None:
        """Returns True when codex is in PATH."""
        mock_which.return_value = "/usr/local/bin/codex"

        assert CodexAdapter.is_codex_available() is True
        mock_which.assert_called_once_with("codex")

    @patch("shutil.which")
    def test_codex_not_available(self, mock_which) -> None:
        """Returns False when codex is not in PATH."""
        mock_which.return_value = None

        assert CodexAdapter.is_codex_available() is False


class TestCodexAdapterMachineId:
    """Tests for machine ID handling."""

    def test_get_machine_id_cached(self) -> None:
        """Machine ID is cached after first call."""
        adapter = CodexAdapter()

        id1 = adapter._get_machine_id()
        id2 = adapter._get_machine_id()

        assert id1 == id2
        assert adapter._machine_id == id1


class TestCodexAdapterAttachDetach:
    """Tests for attach/detach from client."""

    def test_attach_to_client(self) -> None:
        """Attaching registers notification handlers."""
        adapter = CodexAdapter()
        mock_client = MagicMock()

        adapter.attach_to_client(mock_client)

        assert adapter._attached is True
        assert adapter._codex_client is mock_client

        # Should register handlers for tracking events
        calls = mock_client.add_notification_handler.call_args_list
        methods_registered = [c[0][0] for c in calls]
        assert "thread/started" in methods_registered
        assert "turn/started" in methods_registered
        assert "turn/completed" in methods_registered
        assert "item/completed" in methods_registered

    def test_attach_when_already_attached(self) -> None:
        """Attaching when already attached is a no-op."""
        adapter = CodexAdapter()
        adapter._attached = True
        mock_client = MagicMock()

        adapter.attach_to_client(mock_client)

        mock_client.add_notification_handler.assert_not_called()

    def test_detach_from_client(self) -> None:
        """Detaching removes notification handlers."""
        adapter = CodexAdapter()
        mock_client = MagicMock()

        adapter.attach_to_client(mock_client)
        adapter.detach_from_client()

        assert adapter._attached is False
        assert adapter._codex_client is None

        calls = mock_client.remove_notification_handler.call_args_list
        assert len(calls) == len(CodexAdapter.SESSION_TRACKING_EVENTS)

    def test_detach_when_not_attached(self) -> None:
        """Detaching when not attached is a no-op."""
        adapter = CodexAdapter()

        # Should not raise
        adapter.detach_from_client()


class TestCodexAdapterTranslateToHookEvent:
    """Tests for translate_to_hook_event method."""

    def test_thread_started(self) -> None:
        """Translate thread/started to SESSION_START."""
        adapter = CodexAdapter()

        native_event = {
            "method": "thread/started",
            "params": {
                "thread": {
                    "id": "thr-123",
                    "preview": "Help me with code",
                    "modelProvider": "openai",
                    "createdAt": 1704067200,
                }
            },
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.event_type == HookEventType.SESSION_START
        assert hook_event.session_id == "thr-123"
        assert hook_event.source == SessionSource.CODEX
        assert hook_event.data["preview"] == "Help me with code"
        assert hook_event.data["model_provider"] == "openai"

    def test_thread_archive(self) -> None:
        """Translate thread/archive to SESSION_END."""
        adapter = CodexAdapter()

        native_event = {
            "method": "thread/archive",
            "params": {"threadId": "thr-456"},
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.event_type == HookEventType.SESSION_END
        assert hook_event.session_id == "thr-456"

    def test_turn_started(self) -> None:
        """Translate turn/started to BEFORE_AGENT."""
        adapter = CodexAdapter()

        native_event = {
            "method": "turn/started",
            "params": {
                "threadId": "thr-789",
                "turn": {
                    "id": "turn-1",
                    "status": "inProgress",
                },
            },
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.event_type == HookEventType.BEFORE_AGENT
        assert hook_event.session_id == "thr-789"
        assert hook_event.data["turn_id"] == "turn-1"
        assert hook_event.data["status"] == "inProgress"

    def test_turn_completed(self) -> None:
        """Translate turn/completed to AFTER_AGENT."""
        adapter = CodexAdapter()

        native_event = {
            "method": "turn/completed",
            "params": {
                "threadId": "thr-abc",
                "turn": {
                    "id": "turn-2",
                    "status": "completed",
                    "error": None,
                },
            },
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.event_type == HookEventType.AFTER_AGENT
        assert hook_event.session_id == "thr-abc"
        assert hook_event.data["status"] == "completed"

    def test_item_completed_tool(self) -> None:
        """Translate item/completed for tool items to AFTER_TOOL."""
        adapter = CodexAdapter()

        for item_type in ["commandExecution", "fileChange", "mcpToolCall"]:
            native_event = {
                "method": "item/completed",
                "params": {
                    "threadId": "thr-tool",
                    "item": {
                        "id": "item-1",
                        "type": item_type,
                        "status": "completed",
                    },
                },
            }

            hook_event = adapter.translate_to_hook_event(native_event)

            assert hook_event is not None
            assert hook_event.event_type == HookEventType.AFTER_TOOL
            assert hook_event.data["item_type"] == item_type

    def test_item_completed_non_tool(self) -> None:
        """item/completed for non-tool items returns None."""
        adapter = CodexAdapter()

        native_event = {
            "method": "item/completed",
            "params": {
                "threadId": "thr-msg",
                "item": {
                    "id": "item-2",
                    "type": "agentMessage",  # Not a tool type
                    "status": "completed",
                },
            },
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is None

    def test_unknown_event(self) -> None:
        """Unknown event types return None."""
        adapter = CodexAdapter()

        native_event = {
            "method": "unknown/event",
            "params": {},
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is None


class TestCodexAdapterTranslateApprovalEvent:
    """Tests for _translate_approval_event method."""

    def test_command_execution_approval(self) -> None:
        """Translate command execution approval request."""
        adapter = CodexAdapter()

        hook_event = adapter._translate_approval_event(
            "item/commandExecution/requestApproval",
            {
                "threadId": "thr-cmd",
                "itemId": "item-cmd",
                "turnId": "turn-1",
                "parsedCmd": "rm -rf /",
                "reason": "destructive operation",
                "risk": "high",
            },
        )

        assert hook_event is not None
        assert hook_event.event_type == HookEventType.BEFORE_TOOL
        assert hook_event.session_id == "thr-cmd"
        assert hook_event.data["tool_name"] == "Bash"
        assert hook_event.data["tool_input"] == "rm -rf /"
        assert hook_event.metadata["requires_response"] is True

    def test_file_change_approval(self) -> None:
        """Translate file change approval request."""
        adapter = CodexAdapter()

        changes = [{"path": "/file.txt", "content": "new content"}]
        hook_event = adapter._translate_approval_event(
            "item/fileChange/requestApproval",
            {
                "threadId": "thr-file",
                "itemId": "item-file",
                "changes": changes,
            },
        )

        assert hook_event is not None
        assert hook_event.data["tool_name"] == "Write"
        assert hook_event.data["tool_input"] == changes

    def test_unknown_approval_method(self) -> None:
        """Unknown approval method returns None."""
        adapter = CodexAdapter()

        hook_event = adapter._translate_approval_event(
            "unknown/requestApproval",
            {"threadId": "thr-1"},
        )

        assert hook_event is None


class TestCodexAdapterTranslateFromHookResponse:
    """Tests for translate_from_hook_response method."""

    def test_allow_response(self) -> None:
        """Allow response maps to accept."""
        adapter = CodexAdapter()

        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response)

        assert result["decision"] == "accept"

    def test_deny_response(self) -> None:
        """Deny response maps to decline."""
        adapter = CodexAdapter()

        response = HookResponse(decision="deny")
        result = adapter.translate_from_hook_response(response)

        assert result["decision"] == "decline"

    def test_block_response(self) -> None:
        """Block response maps to accept (only 'deny' maps to decline)."""
        adapter = CodexAdapter()

        # Note: The Codex adapter only maps "deny" to "decline"
        # All other decisions (including "block") map to "accept"
        response = HookResponse(decision="block")
        result = adapter.translate_from_hook_response(response)

        # This is the actual behavior - block maps to accept
        assert result["decision"] == "accept"

    def test_other_decisions_map_to_accept(self) -> None:
        """Non-deny decisions map to accept."""
        adapter = CodexAdapter()

        for decision in ["allow", "ask", "modify"]:
            response = HookResponse(decision=decision)
            result = adapter.translate_from_hook_response(response)
            assert result["decision"] == "accept"


class TestCodexAdapterParseTimestamp:
    """Tests for _parse_timestamp method."""

    def test_valid_timestamp(self) -> None:
        """Parse valid Unix timestamp."""
        adapter = CodexAdapter()

        # 1704067200 = 2024-01-01 00:00:00 UTC
        # Note: _parse_timestamp returns local time, not UTC
        dt = adapter._parse_timestamp(1704067200)

        # Just verify it parsed successfully and returns a datetime
        # The exact year depends on timezone
        assert dt is not None
        assert hasattr(dt, "year")
        # The timestamp should be in late Dec 2023 or early Jan 2024 depending on timezone
        assert dt.year in (2023, 2024)

    def test_none_timestamp(self) -> None:
        """None timestamp returns now."""
        adapter = CodexAdapter()

        dt = adapter._parse_timestamp(None)

        # Should be close to now
        assert (datetime.now(UTC) - dt).total_seconds() < 5

    def test_invalid_timestamp(self) -> None:
        """Invalid timestamp returns now."""
        adapter = CodexAdapter()

        dt = adapter._parse_timestamp(-999999999999999)  # Invalid

        assert (datetime.now(UTC) - dt).total_seconds() < 5


class TestCodexAdapterHandleNotification:
    """Tests for _handle_notification callback."""

    def test_handle_notification_processes_event(self) -> None:
        """Notification is processed through hook manager."""
        mock_hook_manager = MagicMock()
        adapter = CodexAdapter(hook_manager=mock_hook_manager)

        adapter._handle_notification(
            "turn/started",
            {"threadId": "thr-1", "turn": {"id": "turn-1", "status": "inProgress"}},
        )

        mock_hook_manager.handle.assert_called_once()
        call_args = mock_hook_manager.handle.call_args[0]
        assert call_args[0].event_type == HookEventType.BEFORE_AGENT

    def test_handle_notification_without_hook_manager(self) -> None:
        """Notification without hook manager is silently ignored."""
        adapter = CodexAdapter()

        # Should not raise
        adapter._handle_notification("turn/started", {"threadId": "thr-1"})

    def test_handle_notification_error_handling(self) -> None:
        """Errors in notification handling are caught."""
        mock_hook_manager = MagicMock()
        mock_hook_manager.handle.side_effect = Exception("Processing error")
        adapter = CodexAdapter(hook_manager=mock_hook_manager)

        # Should not raise
        adapter._handle_notification("turn/started", {"threadId": "thr-1"})


class TestCodexAdapterSyncExistingSessions:
    """Tests for sync_existing_sessions method."""

    @pytest.mark.asyncio
    async def test_sync_without_hook_manager(self):
        """Sync without hook manager returns 0."""
        adapter = CodexAdapter()

        result = await adapter.sync_existing_sessions()

        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_without_client(self):
        """Sync without client returns 0."""
        adapter = CodexAdapter(hook_manager=MagicMock())

        result = await adapter.sync_existing_sessions()

        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_when_client_not_connected(self):
        """Sync when client not connected returns 0."""
        adapter = CodexAdapter(hook_manager=MagicMock())
        mock_client = MagicMock()
        mock_client.is_connected = False
        adapter._codex_client = mock_client

        result = await adapter.sync_existing_sessions()

        assert result == 0

    @pytest.mark.asyncio
    async def test_sync_existing_sessions_success(self):
        """Sync processes threads through hook manager."""
        mock_hook_manager = MagicMock()
        adapter = CodexAdapter(hook_manager=mock_hook_manager)

        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.list_threads = AsyncMock(
            return_value=(
                [
                    CodexThread(id="thr-1", preview="Thread 1", created_at=1000),
                    CodexThread(id="thr-2", preview="Thread 2", created_at=2000),
                ],
                None,  # No next cursor
            )
        )
        adapter._codex_client = mock_client
        adapter._attached = True

        result = await adapter.sync_existing_sessions()

        assert result == 2
        assert mock_hook_manager.handle.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_handles_pagination(self):
        """Sync handles multiple pages of threads."""
        mock_hook_manager = MagicMock()
        adapter = CodexAdapter(hook_manager=mock_hook_manager)

        mock_client = MagicMock()
        mock_client.is_connected = True

        # Return two pages
        page1 = ([CodexThread(id="thr-1")], "cursor-1")
        page2 = ([CodexThread(id="thr-2")], None)

        mock_client.list_threads = AsyncMock(side_effect=[page1, page2])
        adapter._codex_client = mock_client
        adapter._attached = True

        result = await adapter.sync_existing_sessions()

        assert result == 2
        assert mock_client.list_threads.call_count == 2


# =============================================================================
# CodexNotifyAdapter Tests
# =============================================================================


class TestCodexNotifyAdapterInit:
    """Tests for CodexNotifyAdapter initialization."""

    def test_default_init(self) -> None:
        """Default initialization."""
        adapter = CodexNotifyAdapter()

        assert adapter._hook_manager is None
        assert adapter._machine_id is None
        assert adapter._seen_threads == OrderedDict()
        assert adapter.source == SessionSource.CODEX

    def test_with_hook_manager(self) -> None:
        """Initialize with hook manager."""
        mock_hook_manager = MagicMock()
        adapter = CodexNotifyAdapter(hook_manager=mock_hook_manager)

        assert adapter._hook_manager is mock_hook_manager


class TestCodexNotifyAdapterFindJsonlPath:
    """Tests for _find_jsonl_path method."""

    def test_find_jsonl_path_not_exists(self) -> None:
        """Returns None when sessions dir doesn't exist."""
        adapter = CodexNotifyAdapter()

        with patch.object(Path, "exists", return_value=False):
            result = adapter._find_jsonl_path("thread-123")

        assert result is None

    def test_find_jsonl_path_found(self) -> None:
        """Returns path when file found."""
        adapter = CodexNotifyAdapter()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake session file
            session_file = Path(tmpdir) / "2024" / "01" / "01" / "rollout-123-thread-abc.jsonl"
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.touch()

            with (
                patch.object(Path, "exists", return_value=True),
                patch("gobby.adapters.codex_impl.client.CODEX_SESSIONS_DIR", Path(tmpdir)),
                patch(
                    "gobby.adapters.codex_impl.adapter.glob_module.glob",
                    return_value=[str(session_file)],
                ),
            ):
                result = adapter._find_jsonl_path("thread-abc")

            assert result == str(session_file)


class TestCodexNotifyAdapterGetFirstPrompt:
    """Tests for _get_first_prompt method."""

    def test_get_first_prompt_string(self) -> None:
        """Extract first prompt from string list."""
        adapter = CodexNotifyAdapter()

        result = adapter._get_first_prompt(["Hello world", "Second message"])

        assert result == "Hello world"

    def test_get_first_prompt_dict_text(self) -> None:
        """Extract first prompt from dict with text key."""
        adapter = CodexNotifyAdapter()

        result = adapter._get_first_prompt([{"text": "Help me code"}])

        assert result == "Help me code"

    def test_get_first_prompt_dict_content(self) -> None:
        """Extract first prompt from dict with content key."""
        adapter = CodexNotifyAdapter()

        result = adapter._get_first_prompt([{"content": "Fix this bug"}])

        assert result == "Fix this bug"

    def test_get_first_prompt_empty(self) -> None:
        """Returns None for empty list."""
        adapter = CodexNotifyAdapter()

        result = adapter._get_first_prompt([])

        assert result is None

    def test_get_first_prompt_none(self) -> None:
        """Returns None for None input."""
        adapter = CodexNotifyAdapter()

        result = adapter._get_first_prompt(None)

        assert result is None


class TestCodexNotifyAdapterTranslateToHookEvent:
    """Tests for translate_to_hook_event method."""

    def test_translate_agent_turn_complete(self) -> None:
        """Translate agent-turn-complete to AFTER_AGENT."""
        adapter = CodexNotifyAdapter()

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thread-123",
                "event_type": "agent-turn-complete",
                "last_message": "I completed the task",
                "input_messages": ["Help me refactor"],
                "cwd": "/project/path",
                "turn_id": "1",
            },
            "source": "codex",
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is not None
        assert hook_event.event_type == HookEventType.AFTER_AGENT
        assert hook_event.session_id == "thread-123"
        assert hook_event.source == SessionSource.CODEX
        assert hook_event.data["cwd"] == "/project/path"
        assert hook_event.data["last_message"] == "I completed the task"
        assert hook_event.data["is_first_event"] is True
        assert hook_event.data["prompt"] == "Help me refactor"

    def test_translate_missing_thread_id(self) -> None:
        """Returns None when thread_id is missing."""
        adapter = CodexNotifyAdapter()

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "event_type": "agent-turn-complete",
            },
            "source": "codex",
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event is None

    def test_translate_tracks_seen_threads(self) -> None:
        """Adapter tracks seen threads for is_first_event."""
        adapter = CodexNotifyAdapter()

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thread-456",
                "event_type": "agent-turn-complete",
                "input_messages": ["First prompt"],
            },
            "source": "codex",
        }

        # First event
        event1 = adapter.translate_to_hook_event(native_event)
        assert event1.data["is_first_event"] is True
        assert event1.data["prompt"] == "First prompt"

        # Second event for same thread
        event2 = adapter.translate_to_hook_event(native_event)
        assert event2.data["is_first_event"] is False
        assert event2.data["prompt"] is None

    def test_translate_uses_cwd_fallback(self) -> None:
        """Uses current working directory when cwd not provided."""
        adapter = CodexNotifyAdapter()

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thread-789",
                "event_type": "agent-turn-complete",
            },
            "source": "codex",
        }

        hook_event = adapter.translate_to_hook_event(native_event)

        assert hook_event.data["cwd"] == os.getcwd()


class TestCodexNotifyAdapterTranslateFromHookResponse:
    """Tests for translate_from_hook_response method."""

    def test_translate_response(self) -> None:
        """Translate response to simple status dict."""
        adapter = CodexNotifyAdapter()

        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response)

        assert result["status"] == "processed"
        assert result["decision"] == "allow"

    def test_translate_deny_response(self) -> None:
        """Translate deny response."""
        adapter = CodexNotifyAdapter()

        response = HookResponse(decision="deny", reason="Not allowed")
        result = adapter.translate_from_hook_response(response)

        assert result["status"] == "processed"
        assert result["decision"] == "deny"


class TestCodexNotifyAdapterHandleNative:
    """Tests for handle_native method."""

    def test_handle_native_success(self) -> None:
        """Handle native event through hook manager."""
        adapter = CodexNotifyAdapter()
        mock_hook_manager = MagicMock()
        mock_hook_manager.handle.return_value = HookResponse(decision="allow")

        native_event = {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thread-handle",
                "event_type": "agent-turn-complete",
            },
            "source": "codex",
        }

        result = adapter.handle_native(native_event, mock_hook_manager)

        mock_hook_manager.handle.assert_called_once()
        assert result["status"] == "processed"
        assert result["decision"] == "allow"

    def test_handle_native_unsupported_event(self) -> None:
        """Handle unsupported event returns skipped."""
        adapter = CodexNotifyAdapter()
        mock_hook_manager = MagicMock()

        native_event = {
            "hook_type": "Unknown",
            "input_data": {},
            "source": "codex",
        }

        result = adapter.handle_native(native_event, mock_hook_manager)

        mock_hook_manager.handle.assert_not_called()
        assert result["status"] == "skipped"


# =============================================================================
# Integration Tests
# =============================================================================


class TestCodexAdapterEventMapping:
    """Tests verifying event type mapping constants."""

    def test_event_map_contains_all_supported_events(self) -> None:
        """EVENT_MAP contains all events we claim to support."""
        expected_methods = [
            "thread/started",
            "thread/archive",
            "turn/started",
            "turn/completed",
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/completed",
        ]

        for method in expected_methods:
            assert method in CodexAdapter.EVENT_MAP

    def test_tool_item_types_complete(self) -> None:
        """TOOL_ITEM_TYPES contains all tool-related item types."""
        assert "commandExecution" in CodexAdapter.TOOL_ITEM_TYPES
        assert "fileChange" in CodexAdapter.TOOL_ITEM_TYPES
        assert "mcpToolCall" in CodexAdapter.TOOL_ITEM_TYPES

    def test_session_tracking_events_complete(self) -> None:
        """SESSION_TRACKING_EVENTS contains necessary events."""
        assert "thread/started" in CodexAdapter.SESSION_TRACKING_EVENTS
        assert "turn/started" in CodexAdapter.SESSION_TRACKING_EVENTS
        assert "turn/completed" in CodexAdapter.SESSION_TRACKING_EVENTS
        assert "item/completed" in CodexAdapter.SESSION_TRACKING_EVENTS


# =============================================================================
# Phase 1: Approval Response Loop Tests
#
# Tests for bidirectional hook support via the Codex app-server protocol.
# Codex sends approval requests as JSON-RPC requests (with both id and method),
# which must be detected, routed to a handler, and responded to.
# =============================================================================


class TestCodexClientApprovalHandlerRegistration:
    """Tests for approval handler registration on CodexAppServerClient."""

    def test_no_approval_handler_by_default(self) -> None:
        """No approval handler registered by default."""
        client = CodexAppServerClient()
        assert client._approval_handler is None

    def test_register_approval_handler(self) -> None:
        """Register an approval handler."""
        client = CodexAppServerClient()

        async def handler(method: str, params: dict) -> dict:
            return {"decision": "accept"}

        client.register_approval_handler(handler)
        assert client._approval_handler is handler

    def test_register_replaces_previous_handler(self) -> None:
        """Registering a new handler replaces the previous one."""
        client = CodexAppServerClient()

        async def handler1(method: str, params: dict) -> dict:
            return {"decision": "accept"}

        async def handler2(method: str, params: dict) -> dict:
            return {"decision": "decline"}

        client.register_approval_handler(handler1)
        client.register_approval_handler(handler2)
        assert client._approval_handler is handler2

    def test_register_none_clears_handler(self) -> None:
        """Registering None clears the handler."""
        client = CodexAppServerClient()

        async def handler(method: str, params: dict) -> dict:
            return {"decision": "accept"}

        client.register_approval_handler(handler)
        client.register_approval_handler(None)
        assert client._approval_handler is None


class TestCodexClientApprovalRequestDetection:
    """Tests for approval request detection in reader loop.

    Codex sends approval requests as JSON-RPC requests (both id AND method).
    The reader loop must detect these as incoming requests (not responses to
    our outgoing requests) and route them to the registered approval handler.
    """

    @pytest.mark.asyncio
    async def test_detects_command_execution_approval(self) -> None:
        """Reader detects commandExecution approval and calls handler."""
        client = CodexAppServerClient()
        received: dict = {}

        async def handler(method: str, params: dict) -> dict:
            received["method"] = method
            received["params"] = params
            return {"decision": "accept"}

        client.register_approval_handler(handler)

        approval_msg = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thr-test",
                "itemId": "item-1",
                "parsedCmd": "ls -la",
                "reason": "tool use",
            },
        }

        mock_process = MagicMock()
        lines = [json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        assert received["method"] == "item/commandExecution/requestApproval"
        assert received["params"]["threadId"] == "thr-test"
        assert received["params"]["parsedCmd"] == "ls -la"

    @pytest.mark.asyncio
    async def test_detects_file_change_approval(self) -> None:
        """Reader detects fileChange approval request."""
        client = CodexAppServerClient()
        received: dict = {}

        async def handler(method: str, params: dict) -> dict:
            received["method"] = method
            received["params"] = params
            return {"decision": "accept"}

        client.register_approval_handler(handler)

        approval_msg = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "item/fileChange/requestApproval",
            "params": {
                "threadId": "thr-file",
                "changes": [{"path": "/test.txt", "content": "hello"}],
            },
        }

        mock_process = MagicMock()
        lines = [json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        assert received["method"] == "item/fileChange/requestApproval"
        assert received["params"]["changes"][0]["path"] == "/test.txt"

    @pytest.mark.asyncio
    async def test_distinguishes_approval_from_response(self) -> None:
        """Incoming requests (id+method) don't interfere with pending response futures."""
        client = CodexAppServerClient()
        handler_called = False

        async def handler(method: str, params: dict) -> dict:
            nonlocal handler_called
            handler_called = True
            return {"decision": "accept"}

        client.register_approval_handler(handler)

        # Our outgoing request has id=1
        loop = asyncio.get_event_loop()
        pending_future = loop.create_future()
        client._pending_requests[1] = pending_future

        # Two messages: response to our request (id=1) + approval request (id=42)
        response_msg = {"jsonrpc": "2.0", "id": 1, "result": {"key": "value"}}
        approval_msg = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr-1", "parsedCmd": "echo hi"},
        }

        mock_process = MagicMock()
        lines = [json.dumps(response_msg) + "\n", json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        # Response resolved our pending future
        assert pending_future.done()
        assert pending_future.result() == {"key": "value"}

        # Approval handler was called separately
        assert handler_called

    @pytest.mark.asyncio
    async def test_no_handler_sends_error_response(self) -> None:
        """Without approval handler, incoming requests get a JSON-RPC error."""
        client = CodexAppServerClient()

        approval_msg = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr-1"},
        }

        mock_process = MagicMock()
        lines = [json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        # Error response sent back with -32601 (method not found)
        mock_process.stdin.write.assert_called_once()
        sent = json.loads(mock_process.stdin.write.call_args[0][0])
        assert sent["jsonrpc"] == "2.0"
        assert sent["id"] == 42
        assert sent["error"]["code"] == -32601


class TestCodexClientApprovalResponseRouting:
    """Tests for approval response routing back to Codex.

    After the approval handler returns a decision, the client must send
    a JSON-RPC response back to Codex with the matching request id.
    """

    @pytest.mark.asyncio
    async def test_sends_accept_response(self) -> None:
        """Accept decision sends JSON-RPC response with accept."""
        client = CodexAppServerClient()
        written_lines: list[str] = []

        async def handler(method: str, params: dict) -> dict:
            return {"decision": "accept"}

        client.register_approval_handler(handler)

        approval_msg = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr-1", "parsedCmd": "echo test"},
        }

        mock_process = MagicMock()
        lines = [json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = lambda x: written_lines.append(x)
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        assert len(written_lines) >= 1
        response = json.loads(written_lines[0].strip())
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 42
        assert response["result"]["decision"] == "accept"

    @pytest.mark.asyncio
    async def test_sends_decline_response(self) -> None:
        """Decline decision sends JSON-RPC response with decline."""
        client = CodexAppServerClient()
        written_lines: list[str] = []

        async def handler(method: str, params: dict) -> dict:
            return {"decision": "decline"}

        client.register_approval_handler(handler)

        approval_msg = {
            "jsonrpc": "2.0",
            "id": 55,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr-1", "parsedCmd": "rm -rf /"},
        }

        mock_process = MagicMock()
        lines = [json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = lambda x: written_lines.append(x)
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        response = json.loads(written_lines[0].strip())
        assert response["id"] == 55
        assert response["result"]["decision"] == "decline"

    @pytest.mark.asyncio
    async def test_handler_error_sends_error_response(self) -> None:
        """Handler exception sends JSON-RPC error response."""
        client = CodexAppServerClient()
        written_lines: list[str] = []

        async def handler(method: str, params: dict) -> dict:
            raise RuntimeError("Hook processing failed")

        client.register_approval_handler(handler)

        approval_msg = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr-1"},
        }

        mock_process = MagicMock()
        lines = [json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = lambda x: written_lines.append(x)
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        assert len(written_lines) >= 1
        response = json.loads(written_lines[0].strip())
        assert response["id"] == 10
        assert "error" in response
        assert response["error"]["code"] == -32603  # Internal error
        assert "Hook processing failed" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_response_preserves_request_id(self) -> None:
        """Response id matches the incoming request id."""
        client = CodexAppServerClient()
        written_lines: list[str] = []

        async def handler(method: str, params: dict) -> dict:
            return {"decision": "accept"}

        client.register_approval_handler(handler)

        approval_msg = {
            "jsonrpc": "2.0",
            "id": 99999,
            "method": "item/fileChange/requestApproval",
            "params": {"threadId": "thr-1", "changes": []},
        }

        mock_process = MagicMock()
        lines = [json.dumps(approval_msg) + "\n"]
        read_idx = 0

        def mock_readline():
            nonlocal read_idx
            if read_idx < len(lines):
                line = lines[read_idx]
                read_idx += 1
                return line
            return ""

        mock_process.stdout.readline = mock_readline
        mock_process.poll.return_value = 0
        mock_process.stdin.write = lambda x: written_lines.append(x)
        mock_process.stdin.flush = MagicMock()

        client._process = mock_process
        client._state = CodexConnectionState.CONNECTED

        reader_task = asyncio.create_task(client._read_loop())
        await asyncio.wait_for(reader_task, timeout=2.0)

        response = json.loads(written_lines[0].strip())
        assert response["id"] == 99999


class TestCodexAdapterApprovalHandling:
    """Tests for CodexAdapter.handle_approval_request with HookManager."""

    @pytest.mark.asyncio
    async def test_handle_approval_calls_hook_manager(self) -> None:
        """handle_approval_request translates and processes through HookManager."""
        mock_hm = MagicMock()
        mock_hm.handle.return_value = HookResponse(decision="allow")
        adapter = CodexAdapter(hook_manager=mock_hm)

        result = await adapter.handle_approval_request(
            "item/commandExecution/requestApproval",
            {"threadId": "thr-cmd", "itemId": "item-1", "parsedCmd": "echo hello"},
        )

        mock_hm.handle.assert_called_once()
        hook_event = mock_hm.handle.call_args[0][0]
        assert hook_event.event_type == HookEventType.BEFORE_TOOL
        assert hook_event.data["tool_name"] == "Bash"
        assert result == {"decision": "accept"}

    @pytest.mark.asyncio
    async def test_handle_approval_deny_maps_to_decline(self) -> None:
        """Denied hook response translates to decline."""
        mock_hm = MagicMock()
        mock_hm.handle.return_value = HookResponse(decision="deny")
        adapter = CodexAdapter(hook_manager=mock_hm)

        result = await adapter.handle_approval_request(
            "item/commandExecution/requestApproval",
            {"threadId": "thr-1", "parsedCmd": "rm -rf /"},
        )

        assert result == {"decision": "decline"}

    @pytest.mark.asyncio
    async def test_handle_approval_without_hook_manager(self) -> None:
        """Without hook manager, defaults to accept."""
        adapter = CodexAdapter()

        result = await adapter.handle_approval_request(
            "item/commandExecution/requestApproval",
            {"threadId": "thr-1", "parsedCmd": "ls"},
        )

        assert result == {"decision": "accept"}

    @pytest.mark.asyncio
    async def test_handle_approval_unknown_method(self) -> None:
        """Unknown approval method defaults to accept."""
        mock_hm = MagicMock()
        adapter = CodexAdapter(hook_manager=mock_hm)

        result = await adapter.handle_approval_request(
            "unknown/requestApproval",
            {"threadId": "thr-1"},
        )

        assert result == {"decision": "accept"}
        mock_hm.handle.assert_not_called()


class TestCodexAdapterApprovalAttach:
    """Tests for approval handler registration during adapter attach."""

    def test_attach_registers_approval_handler(self) -> None:
        """Attaching adapter to client registers approval handler."""
        mock_hm = MagicMock()
        adapter = CodexAdapter(hook_manager=mock_hm)
        mock_client = MagicMock()

        adapter.attach_to_client(mock_client)

        mock_client.register_approval_handler.assert_called_once()


# =============================================================================
# Phase 2: Context Injection Tests
#
# Tests for injecting session metadata and workflow context into Codex turns.
# Codex uses turn-start injection: context is prepended to the `instructions`
# field when starting a turn, unlike Claude/Gemini which use per-hook
# additionalContext.
# =============================================================================


class TestCodexClientContextPrefixParameter:
    """Tests for context_prefix parameter in start_turn().

    The client should accept a context_prefix string and prepend it to
    the instructions field in the turn/start JSON-RPC request.
    """

    @pytest.mark.asyncio
    async def test_start_turn_without_context_prefix(self) -> None:
        """start_turn without context_prefix sends no instructions field."""
        client = CodexAppServerClient()

        mock_result = {"turn": {"id": "turn-1", "status": "inProgress", "items": []}}

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            await client.start_turn("thr-1", "Help me refactor")

            params = mock_send.call_args[0][1]
            # No instructions field when no context_prefix
            assert "instructions" not in params

    @pytest.mark.asyncio
    async def test_start_turn_with_context_prefix(self) -> None:
        """start_turn with context_prefix adds instructions field."""
        client = CodexAppServerClient()

        mock_result = {"turn": {"id": "turn-2", "status": "inProgress", "items": []}}

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            await client.start_turn(
                "thr-1",
                "Help me refactor",
                context_prefix="Gobby Session ID: #42",
            )

            params = mock_send.call_args[0][1]
            assert "instructions" in params
            assert "Gobby Session ID: #42" in params["instructions"]

    @pytest.mark.asyncio
    async def test_start_turn_context_prefix_none_omits_instructions(self) -> None:
        """start_turn with context_prefix=None sends no instructions field."""
        client = CodexAppServerClient()

        mock_result = {"turn": {"id": "turn-3", "status": "inProgress", "items": []}}

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            await client.start_turn(
                "thr-1",
                "Help me refactor",
                context_prefix=None,
            )

            params = mock_send.call_args[0][1]
            assert "instructions" not in params

    @pytest.mark.asyncio
    async def test_start_turn_context_prefix_empty_string_omits_instructions(self) -> None:
        """start_turn with empty context_prefix sends no instructions field."""
        client = CodexAppServerClient()

        mock_result = {"turn": {"id": "turn-4", "status": "inProgress", "items": []}}

        with patch.object(
            client, "_send_request", new_callable=AsyncMock, return_value=mock_result
        ) as mock_send:
            await client.start_turn(
                "thr-1",
                "Help me refactor",
                context_prefix="",
            )

            params = mock_send.call_args[0][1]
            assert "instructions" not in params


class TestCodexAdapterContextStringBuilding:
    """Tests for context string building in CodexAdapter.

    The adapter should build context strings from HookResponse metadata,
    similar to Claude/Gemini adapters, for injection into Codex turns.
    translate_from_hook_response() should include context for BEFORE_AGENT hooks.
    """

    def test_translate_response_includes_context(self) -> None:
        """translate_from_hook_response includes context from HookResponse."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            context="Workflow step: implement-code",
        )
        result = adapter.translate_from_hook_response(response)

        assert "context" in result
        assert "Workflow step: implement-code" in result["context"]

    def test_translate_response_includes_session_metadata(self) -> None:
        """translate_from_hook_response includes session metadata for first hook."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "plat-uuid-123",
                "session_ref": "#42",
                "external_id": "thr-codex-abc",
                "_first_hook_for_session": True,
            },
        )
        result = adapter.translate_from_hook_response(response)

        assert "context" in result
        context = result["context"]
        assert "Gobby Session ID:" in context
        assert "#42" in context

    def test_translate_response_minimal_metadata_subsequent_hooks(self) -> None:
        """Subsequent hooks only inject minimal session ref."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "plat-uuid-123",
                "session_ref": "#42",
                "_first_hook_for_session": False,
            },
        )
        result = adapter.translate_from_hook_response(response)

        assert "context" in result
        context = result["context"]
        assert "Gobby Session ID: #42" in context
        # Should NOT contain full metadata
        assert "external_id" not in context.lower()

    def test_translate_response_no_context_when_no_metadata(self) -> None:
        """No context field when no metadata or context."""
        adapter = CodexAdapter()

        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response)

        # Should only have decision field
        assert result == {"decision": "accept"}

    def test_translate_response_first_hook_full_metadata(self) -> None:
        """First hook includes full session metadata (project, machine, etc.)."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "plat-uuid-456",
                "session_ref": "#99",
                "external_id": "thr-codex-xyz",
                "machine_id": "machine-abc",
                "project_id": "proj-def",
                "_first_hook_for_session": True,
            },
        )
        result = adapter.translate_from_hook_response(response)

        context = result["context"]
        assert "#99" in context
        assert "plat-uuid-456" in context
        assert "thr-codex-xyz" in context
        assert "machine-abc" in context
        assert "proj-def" in context

    def test_translate_response_combines_context_and_metadata(self) -> None:
        """Both workflow context and session metadata are combined."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            context="Active workflow: auto-task",
            metadata={
                "session_id": "plat-uuid-789",
                "session_ref": "#100",
                "_first_hook_for_session": True,
            },
        )
        result = adapter.translate_from_hook_response(response)

        context = result["context"]
        assert "Active workflow: auto-task" in context
        assert "Gobby Session ID:" in context
        assert "#100" in context


class TestCodexAdapterContextOneTimeInjection:
    """Tests for one-time context injection behavior.

    Context metadata should only be injected fully on the first hook
    per session. Subsequent hooks should only include minimal session ref.
    This matches the behavior in Claude/Gemini adapters.
    """

    def test_first_hook_flag_controls_metadata_depth(self) -> None:
        """_first_hook_for_session=True triggers full metadata injection."""
        adapter = CodexAdapter()

        # First hook - full metadata
        first_response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "plat-1",
                "session_ref": "#50",
                "external_id": "thr-ext-1",
                "machine_id": "m-1",
                "_first_hook_for_session": True,
            },
        )
        first_result = adapter.translate_from_hook_response(first_response)

        # Subsequent hook - minimal metadata
        subsequent_response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "plat-1",
                "session_ref": "#50",
                "external_id": "thr-ext-1",
                "machine_id": "m-1",
                "_first_hook_for_session": False,
            },
        )
        subsequent_result = adapter.translate_from_hook_response(subsequent_response)

        # First should be fuller than subsequent
        first_context = first_result.get("context", "")
        subsequent_context = subsequent_result.get("context", "")

        assert len(first_context) > len(subsequent_context)
        # First has external_id
        assert "thr-ext-1" in first_context
        # Subsequent does not
        assert "thr-ext-1" not in subsequent_context

    def test_no_session_id_means_no_context_injection(self) -> None:
        """Without session_id in metadata, no context is injected."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            metadata={
                "_first_hook_for_session": True,
                # No session_id
            },
        )
        result = adapter.translate_from_hook_response(response)

        # No context injected without session_id
        assert result == {"decision": "accept"}


class TestCodexAdapterContextFormat:
    """Tests for context format consistency with Claude/Gemini adapters.

    The Codex adapter should produce context strings that follow the same
    patterns as Claude and Gemini adapters for consistency across CLIs.
    """

    def test_session_ref_format(self) -> None:
        """Session ref uses '#N' format in context."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "uuid-123",
                "session_ref": "#77",
                "_first_hook_for_session": True,
            },
        )
        result = adapter.translate_from_hook_response(response)

        context = result["context"]
        # Should contain "Gobby Session ID: #77" similar to Claude/Gemini
        assert "Gobby Session ID: #77" in context

    def test_session_ref_with_full_id(self) -> None:
        """First hook shows both session ref and full UUID."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "uuid-full-456",
                "session_ref": "#88",
                "_first_hook_for_session": True,
            },
        )
        result = adapter.translate_from_hook_response(response)

        context = result["context"]
        # Should include both ref and full ID like Claude adapter
        assert "#88" in context
        assert "uuid-full-456" in context

    def test_external_id_labeled(self) -> None:
        """External ID is labeled as CLI-specific session ID."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="allow",
            metadata={
                "session_id": "plat-id",
                "session_ref": "#10",
                "external_id": "thr-codex-external",
                "_first_hook_for_session": True,
            },
        )
        result = adapter.translate_from_hook_response(response)

        context = result["context"]
        assert "thr-codex-external" in context

    def test_decision_still_present_with_context(self) -> None:
        """Decision field is always present alongside context."""
        adapter = CodexAdapter()

        response = HookResponse(
            decision="deny",
            metadata={
                "session_id": "plat-deny",
                "session_ref": "#5",
                "_first_hook_for_session": True,
            },
        )
        result = adapter.translate_from_hook_response(response)

        assert result["decision"] == "decline"
        assert "context" in result


# =============================================================================
# Phase 3: Workflow Enforcement Tests
#
# Tests for block_tools, task enforcement, and tool name normalization
# working correctly with Codex events. The workflow enforcement engine
# uses event_data["tool_name"] which must be normalized from Codex-native
# names (commandExecution, fileChange) to CC-style names (Bash, Write).
# =============================================================================


class TestCodexToolNameNormalization:
    """Tests for Codex tool name normalization via TOOL_MAP.

    The adapter normalizes Codex tool names to Claude Code conventions
    so block_tools rules work consistently across CLIs.
    """

    def test_command_execution_maps_to_bash(self) -> None:
        """commandExecution normalizes to Bash."""
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("commandExecution") == "Bash"

    def test_read_file_variants_map_to_read(self) -> None:
        """read_file and ReadFile normalize to Read."""
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("read_file") == "Read"
        assert adapter.normalize_tool_name("ReadFile") == "Read"

    def test_write_file_variants_map_to_write(self) -> None:
        """write_file and WriteFile normalize to Write."""
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("write_file") == "Write"
        assert adapter.normalize_tool_name("WriteFile") == "Write"

    def test_edit_file_variants_map_to_edit(self) -> None:
        """edit_file and EditFile normalize to Edit."""
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("edit_file") == "Edit"
        assert adapter.normalize_tool_name("EditFile") == "Edit"

    def test_shell_variants_map_to_bash(self) -> None:
        """Shell command variants normalize to Bash."""
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("run_shell_command") == "Bash"
        assert adapter.normalize_tool_name("RunShellCommand") == "Bash"

    def test_search_tools_normalize(self) -> None:
        """Search tools normalize to Glob/Grep."""
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("glob") == "Glob"
        assert adapter.normalize_tool_name("grep") == "Grep"
        assert adapter.normalize_tool_name("GlobTool") == "Glob"
        assert adapter.normalize_tool_name("GrepTool") == "Grep"

    def test_unknown_tool_passes_through(self) -> None:
        """Unknown tool names pass through unchanged."""
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("customTool") == "customTool"
        assert adapter.normalize_tool_name("myPlugin") == "myPlugin"

    def test_approval_event_uses_normalized_names(self) -> None:
        """Approval events produce normalized tool names in HookEvent."""
        adapter = CodexAdapter()

        # commandExecution should produce "Bash"
        event = adapter._translate_approval_event(
            "item/commandExecution/requestApproval",
            {"threadId": "thr-1", "itemId": "item-1", "parsedCmd": "ls"},
        )
        assert event is not None
        assert event.data["tool_name"] == "Bash"

        # fileChange should produce "Write"
        event = adapter._translate_approval_event(
            "item/fileChange/requestApproval",
            {"threadId": "thr-1", "itemId": "item-2", "changes": []},
        )
        assert event is not None
        assert event.data["tool_name"] == "Write"


class TestCodexBlockToolsEnforcement:
    """Tests for block_tools enforcement with Codex event data.

    The block_tools function evaluates rules against event_data["tool_name"].
    Since Codex normalizes tool names to CC-style, the same block_tools
    rules that work for Claude should work for Codex.
    """

    @pytest.mark.asyncio
    async def test_block_bash_tool_from_codex_event(self) -> None:
        """block_tools blocks Bash tool from Codex approval event."""
        from gobby.workflows.enforcement.blocking import block_tools

        # Simulate event_data from a Codex BEFORE_TOOL hook
        event_data = {
            "tool_name": "Bash",  # Normalized from commandExecution
            "tool_input": "rm -rf /tmp",
            "item_id": "item-1",
        }

        rules = [
            {
                "tools": ["Bash"],
                "reason": "Shell commands are blocked in this workflow step.",
            }
        ]

        result = await block_tools(rules=rules, event_data=event_data)

        assert result is not None
        assert result["decision"] == "block"
        assert "Shell commands are blocked" in result["reason"]

    @pytest.mark.asyncio
    async def test_block_write_tool_from_codex_event(self) -> None:
        """block_tools blocks Write tool from Codex file change event."""
        from gobby.workflows.enforcement.blocking import block_tools

        event_data = {
            "tool_name": "Write",  # Normalized from fileChange
            "tool_input": [{"path": "/test.py", "content": "pass"}],
        }

        rules = [
            {
                "tools": ["Edit", "Write", "NotebookEdit"],
                "reason": "Claim a task before editing files.",
            }
        ]

        result = await block_tools(rules=rules, event_data=event_data)

        assert result is not None
        assert result["decision"] == "block"

    @pytest.mark.asyncio
    async def test_allow_non_blocked_tool(self) -> None:
        """block_tools allows tools not in the block list."""
        from gobby.workflows.enforcement.blocking import block_tools

        event_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/test.py"},
        }

        rules = [
            {
                "tools": ["Edit", "Write"],
                "reason": "Only read operations allowed.",
            }
        ]

        result = await block_tools(rules=rules, event_data=event_data)

        assert result is None  # None means allowed

    @pytest.mark.asyncio
    async def test_block_tools_with_condition(self) -> None:
        """block_tools evaluates conditions against workflow state."""
        from gobby.workflows.definitions import WorkflowState
        from gobby.workflows.enforcement.blocking import block_tools

        state = WorkflowState(
            session_id="sess-test",
            workflow_name="test-workflow",
            step="implement",
            variables={"task_claimed": False},
        )

        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/src/main.py"},
        }

        rules = [
            {
                "tools": ["Edit", "Write"],
                "when": "not task_claimed",
                "reason": "Claim a task first.",
            }
        ]

        result = await block_tools(
            rules=rules, event_data=event_data, workflow_state=state
        )

        assert result is not None
        assert result["decision"] == "block"

    @pytest.mark.asyncio
    async def test_block_tools_condition_not_met_allows(self) -> None:
        """block_tools allows when condition is not met."""
        from gobby.workflows.definitions import WorkflowState
        from gobby.workflows.enforcement.blocking import block_tools

        state = WorkflowState(
            session_id="sess-test",
            workflow_name="test-workflow",
            step="implement",
            variables={"task_claimed": True},
        )

        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/src/main.py"},
        }

        rules = [
            {
                "tools": ["Edit", "Write"],
                "when": "not task_claimed",
                "reason": "Claim a task first.",
            }
        ]

        result = await block_tools(
            rules=rules, event_data=event_data, workflow_state=state
        )

        assert result is None  # Allowed because task_claimed=True


class TestCodexApprovalDeclineFormat:
    """Tests for approval decline response format from Codex adapter.

    When a tool is blocked, the adapter must translate the HookResponse
    with decision="deny" into Codex's {"decision": "decline"} format.
    This ensures the Codex agent receives a proper denial via JSON-RPC.
    """

    @pytest.mark.asyncio
    async def test_blocked_tool_produces_decline(self) -> None:
        """HookManager deny → adapter decline for Codex."""
        mock_hm = MagicMock()
        mock_hm.handle.return_value = HookResponse(
            decision="deny",
            reason="Bash is blocked in this workflow step.",
        )
        adapter = CodexAdapter(hook_manager=mock_hm)

        result = await adapter.handle_approval_request(
            "item/commandExecution/requestApproval",
            {"threadId": "thr-blocked", "parsedCmd": "rm -rf /"},
        )

        assert result == {"decision": "decline"}

    @pytest.mark.asyncio
    async def test_allowed_tool_produces_accept(self) -> None:
        """HookManager allow → adapter accept for Codex."""
        mock_hm = MagicMock()
        mock_hm.handle.return_value = HookResponse(decision="allow")
        adapter = CodexAdapter(hook_manager=mock_hm)

        result = await adapter.handle_approval_request(
            "item/commandExecution/requestApproval",
            {"threadId": "thr-ok", "parsedCmd": "echo hello"},
        )

        assert result == {"decision": "accept"}

    @pytest.mark.asyncio
    async def test_hook_error_defaults_to_accept(self) -> None:
        """Hook processing error defaults to accept (fail-open)."""
        mock_hm = MagicMock()
        mock_hm.handle.side_effect = RuntimeError("Handler crashed")
        adapter = CodexAdapter(hook_manager=mock_hm)

        result = await adapter.handle_approval_request(
            "item/commandExecution/requestApproval",
            {"threadId": "thr-err", "parsedCmd": "ls"},
        )

        assert result == {"decision": "accept"}

    def test_translate_block_to_decline(self) -> None:
        """translate_from_hook_response maps 'block' decision correctly."""
        adapter = CodexAdapter()

        # 'deny' maps to 'decline'
        response = HookResponse(decision="deny")
        result = adapter.translate_from_hook_response(response)
        assert result["decision"] == "decline"

    def test_translate_allow_to_accept(self) -> None:
        """translate_from_hook_response maps 'allow' to 'accept'."""
        adapter = CodexAdapter()

        response = HookResponse(decision="allow")
        result = adapter.translate_from_hook_response(response)
        assert result["decision"] == "accept"


class TestCodexWorkflowEnforcementIntegration:
    """Integration tests verifying end-to-end workflow enforcement for Codex.

    These tests verify that the full chain works:
    1. Codex sends approval request
    2. Adapter translates to HookEvent with normalized tool name
    3. HookManager evaluates workflow rules (block_tools)
    4. Adapter translates HookResponse back to Codex format
    """

    @pytest.mark.asyncio
    async def test_full_chain_blocked_command(self) -> None:
        """Full chain: Codex approval → HookEvent → deny → decline."""
        mock_hm = MagicMock()
        mock_hm.handle.return_value = HookResponse(
            decision="deny",
            reason="Tool blocked by workflow",
        )
        adapter = CodexAdapter(hook_manager=mock_hm)

        # Simulate Codex sending commandExecution approval
        result = await adapter.handle_approval_request(
            "item/commandExecution/requestApproval",
            {
                "threadId": "thr-chain",
                "itemId": "item-chain",
                "turnId": "turn-1",
                "parsedCmd": "pip install malware",
                "reason": "tool use",
                "risk": "high",
            },
        )

        # Verify HookEvent was created correctly
        hook_event = mock_hm.handle.call_args[0][0]
        assert hook_event.event_type == HookEventType.BEFORE_TOOL
        assert hook_event.data["tool_name"] == "Bash"
        assert hook_event.data["tool_input"] == "pip install malware"
        assert hook_event.source == SessionSource.CODEX

        # Verify decline response
        assert result == {"decision": "decline"}

    @pytest.mark.asyncio
    async def test_full_chain_allowed_file_change(self) -> None:
        """Full chain: Codex file change → HookEvent → allow → accept."""
        mock_hm = MagicMock()
        mock_hm.handle.return_value = HookResponse(decision="allow")
        adapter = CodexAdapter(hook_manager=mock_hm)

        changes = [{"path": "/src/app.py", "content": "print('hello')"}]
        result = await adapter.handle_approval_request(
            "item/fileChange/requestApproval",
            {
                "threadId": "thr-file",
                "itemId": "item-file",
                "changes": changes,
            },
        )

        hook_event = mock_hm.handle.call_args[0][0]
        assert hook_event.data["tool_name"] == "Write"
        assert hook_event.data["tool_input"] == changes

        assert result == {"decision": "accept"}
