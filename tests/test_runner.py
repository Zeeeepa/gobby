"""Tests for src/runner.py - Gobby Daemon Runner."""

import signal
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.runner import GobbyRunner, main, run_gobby


@pytest.fixture
def mock_config():
    """Create a mock config with WebSocket disabled by default."""
    config = MagicMock()
    config.daemon_port = 8765
    config.websocket = None
    config.session_lifecycle = MagicMock()
    config.message_tracking = None
    config.memory_sync = MagicMock()
    config.memory_sync.enabled = False
    return config


@pytest.fixture
def mock_config_with_websocket():
    """Create a mock config with WebSocket enabled."""
    config = MagicMock()
    config.daemon_port = 8765
    config.websocket = MagicMock()
    config.websocket.enabled = True
    config.websocket.port = 8766
    config.websocket.ping_interval = 30
    config.websocket.ping_timeout = 10
    config.session_lifecycle = MagicMock()
    config.message_tracking = None
    config.memory_sync = MagicMock()
    config.memory_sync.enabled = False
    return config


def create_base_patches(
    mock_config=None,
    mock_mcp_manager=None,
    mock_http=None,
    mock_ws_server=None,
):
    """Create all standard patches needed for GobbyRunner tests.

    Args:
        mock_config: Optional config mock. If None, uses a default mock.
        mock_mcp_manager: Optional MCPClientManager mock.
        mock_http: Optional HTTPServer mock.
        mock_ws_server: Optional WebSocketServer mock.

    Returns a list of patch objects that should be used with ExitStack.
    """
    # Create default mocks if not provided
    if mock_mcp_manager is None:
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connect_all = AsyncMock()
        mock_mcp_manager.disconnect_all = AsyncMock()

    if mock_http is None:
        mock_http = MagicMock()
        mock_http.app = MagicMock()
        mock_http.port = 8765

    patches = [
        patch("gobby.runner.setup_file_logging"),
        patch("gobby.runner.get_machine_id", return_value="test-machine"),
        patch("gobby.runner.LocalDatabase"),
        patch("gobby.runner.run_migrations"),
        patch("gobby.runner.LocalSessionManager"),
        patch("gobby.runner.LocalSkillManager"),
        patch("gobby.runner.LocalSessionMessageManager"),
        patch("gobby.runner.LocalTaskManager"),
        patch("gobby.runner.SessionTaskManager"),
        patch("gobby.runner.MCPClientManager", return_value=mock_mcp_manager),
        patch("gobby.runner.TaskSyncManager"),
        patch("gobby.runner.MemorySyncManager"),
        patch("gobby.runner.SessionMessageProcessor", return_value=AsyncMock()),
        patch("gobby.runner.TaskExpander"),
        patch("gobby.runner.TaskValidator"),
        patch("gobby.runner.SessionLifecycleManager", return_value=AsyncMock()),
        patch("gobby.runner.create_llm_service", return_value=None),
        patch("gobby.runner.MemoryManager", return_value=None),
        patch("gobby.runner.SkillLearner", return_value=None),
        patch("gobby.runner.HTTPServer", return_value=mock_http),
    ]

    # Add config patch
    if mock_config is not None:
        patches.insert(1, patch("gobby.runner.load_config", return_value=mock_config))
    else:
        patches.insert(1, patch("gobby.runner.load_config"))

    # Add WebSocketServer patch
    if mock_ws_server is not None:
        patches.append(patch("gobby.runner.WebSocketServer", return_value=mock_ws_server))
    else:
        patches.append(patch("gobby.runner.WebSocketServer"))

    return patches


class TestGobbyRunnerInit:
    """Tests for GobbyRunner initialization."""

    def test_init_creates_components(self, tmp_path, mock_config_with_websocket):
        """Test that init creates all required components."""
        patches = create_base_patches(mock_config=mock_config_with_websocket)

        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            mock_http_cls = mocks[-2]
            mock_ws_cls = mocks[-1]

            runner = GobbyRunner(config_path=tmp_path / "config.yaml", verbose=True)

            assert runner.config == mock_config_with_websocket
            assert runner.verbose is True
            assert runner.machine_id == "test-machine"
            assert runner._shutdown_requested is False
            mock_http_cls.assert_called_once()
            mock_ws_cls.assert_called_once()

    def test_init_without_websocket(self, mock_config):
        """Test init when WebSocket is disabled."""
        mock_config.websocket = MagicMock()
        mock_config.websocket.enabled = False

        patches = create_base_patches(mock_config)

        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            mock_ws_cls = mocks[-1]

            runner = GobbyRunner()

            assert runner.websocket_server is None
            mock_ws_cls.assert_not_called()

    def test_init_websocket_none_config(self, mock_config):
        """Test init when websocket config is None."""
        patches = create_base_patches(mock_config)

        with ExitStack() as stack:
            [stack.enter_context(p) for p in patches]

            runner = GobbyRunner()

            assert runner.websocket_server is None


class TestGobbyRunnerSignalHandlers:
    """Tests for signal handler setup."""

    def test_setup_signal_handlers(self, mock_config):
        """Test that signal handlers are registered."""
        patches = create_base_patches(mock_config)

        with ExitStack() as stack:
            [stack.enter_context(p) for p in patches]

            runner = GobbyRunner()

            # Create mock loop
            mock_loop = MagicMock()

            with patch("asyncio.get_running_loop", return_value=mock_loop):
                runner._setup_signal_handlers()

            # Verify signal handlers were added
            assert mock_loop.add_signal_handler.call_count == 2
            calls = mock_loop.add_signal_handler.call_args_list
            signals_registered = [call[0][0] for call in calls]
            assert signal.SIGTERM in signals_registered
            assert signal.SIGINT in signals_registered


class TestGobbyRunnerRun:
    """Tests for the run method."""

    @pytest.mark.asyncio
    async def test_run_connects_mcp_servers(self, mock_config):
        """Test that run connects to MCP servers."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connect_all = AsyncMock()
        mock_mcp_manager.disconnect_all = AsyncMock()

        patches = create_base_patches(
            mock_config=mock_config,
            mock_mcp_manager=mock_mcp_manager,
        )

        with ExitStack() as stack:
            [stack.enter_context(p) for p in patches]

            runner = GobbyRunner()
            runner._shutdown_requested = True

            with patch("uvicorn.Config"), patch("uvicorn.Server") as mock_server_cls:
                mock_server = AsyncMock()
                mock_server.serve = AsyncMock()
                mock_server_cls.return_value = mock_server

                with patch.object(runner, "_setup_signal_handlers"):
                    await runner.run()

            mock_mcp_manager.connect_all.assert_called_once()
            mock_mcp_manager.disconnect_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_handles_mcp_timeout(self, mock_config):
        """Test that run handles MCP connection timeout."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connect_all = AsyncMock(side_effect=TimeoutError())
        mock_mcp_manager.disconnect_all = AsyncMock()

        patches = create_base_patches(
            mock_config=mock_config,
            mock_mcp_manager=mock_mcp_manager,
        )

        with ExitStack() as stack:
            [stack.enter_context(p) for p in patches]

            runner = GobbyRunner()
            runner._shutdown_requested = True

            with patch("uvicorn.Config"), patch("uvicorn.Server") as mock_server_cls:
                mock_server = AsyncMock()
                mock_server.serve = AsyncMock()
                mock_server_cls.return_value = mock_server

                with patch.object(runner, "_setup_signal_handlers"):
                    # Should not raise - timeout is handled gracefully
                    await runner.run()

    @pytest.mark.asyncio
    async def test_run_handles_mcp_connection_error(self, mock_config):
        """Test that run handles MCP connection errors."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connect_all = AsyncMock(side_effect=Exception("Connection failed"))
        mock_mcp_manager.disconnect_all = AsyncMock()

        patches = create_base_patches(
            mock_config=mock_config,
            mock_mcp_manager=mock_mcp_manager,
        )

        with ExitStack() as stack:
            [stack.enter_context(p) for p in patches]

            runner = GobbyRunner()
            runner._shutdown_requested = True

            with patch("uvicorn.Config"), patch("uvicorn.Server") as mock_server_cls:
                mock_server = AsyncMock()
                mock_server.serve = AsyncMock()
                mock_server_cls.return_value = mock_server

                with patch.object(runner, "_setup_signal_handlers"):
                    # Should not raise - error is logged but doesn't crash
                    await runner.run()

    @pytest.mark.asyncio
    async def test_run_with_websocket_server(self, mock_config_with_websocket):
        """Test run with WebSocket server enabled."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connect_all = AsyncMock()
        mock_mcp_manager.disconnect_all = AsyncMock()

        mock_ws_server = AsyncMock()
        mock_ws_server.start = AsyncMock()

        patches = create_base_patches(
            mock_config=mock_config_with_websocket,
            mock_mcp_manager=mock_mcp_manager,
            mock_ws_server=mock_ws_server,
        )

        with ExitStack() as stack:
            [stack.enter_context(p) for p in patches]

            runner = GobbyRunner()
            runner._shutdown_requested = True

            with patch("uvicorn.Config"), patch("uvicorn.Server") as mock_server_cls:
                mock_server = AsyncMock()
                mock_server.serve = AsyncMock()
                mock_server_cls.return_value = mock_server

                with patch.object(runner, "_setup_signal_handlers"):
                    await runner.run()

            # WebSocket server start should be called
            mock_ws_server.start.assert_called()

    @pytest.mark.asyncio
    async def test_run_passes_websocket_to_http(self, mock_config_with_websocket):
        """Test that run passes WebSocket server reference to HTTP server."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connect_all = AsyncMock()
        mock_mcp_manager.disconnect_all = AsyncMock()

        mock_ws_server = AsyncMock()
        mock_ws_server.start = AsyncMock()

        mock_http = MagicMock()
        mock_http.app = MagicMock()
        mock_http.port = 8765

        patches = create_base_patches(
            mock_config=mock_config_with_websocket,
            mock_mcp_manager=mock_mcp_manager,
            mock_http=mock_http,
            mock_ws_server=mock_ws_server,
        )

        with ExitStack() as stack:
            [stack.enter_context(p) for p in patches]

            runner = GobbyRunner()

            # Verify reference was passed
            # In our implementation, we set it on the http_server instance
            assert runner.http_server.websocket_server == mock_ws_server


class TestRunGobbyFunction:
    """Tests for run_gobby async function."""

    @pytest.mark.asyncio
    async def test_run_gobby_creates_runner(self):
        """Test that run_gobby creates and runs GobbyRunner."""
        with patch("gobby.runner.GobbyRunner") as mock_runner_cls:
            mock_runner = AsyncMock()
            mock_runner.run = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            await run_gobby(config_path=Path("/tmp/config.yaml"), verbose=True)

            mock_runner_cls.assert_called_once_with(
                config_path=Path("/tmp/config.yaml"), verbose=True
            )
            mock_runner.run.assert_called_once()


class TestMainFunction:
    """Tests for main synchronous entry point."""

    def test_main_runs_asyncio(self):
        """Test that main runs the async runner."""
        with patch("asyncio.run") as mock_run:
            with patch("gobby.runner.run_gobby") as mock_run_gobby:
                mock_run_gobby.return_value = None
                main(config_path=Path("/tmp/config.yaml"), verbose=True)

            mock_run.assert_called_once()

    def test_main_handles_keyboard_interrupt(self):
        """Test that main handles KeyboardInterrupt gracefully."""
        with patch("asyncio.run", side_effect=KeyboardInterrupt()):
            with patch("gobby.runner.run_gobby") as mock_run_gobby:
                mock_run_gobby.return_value = None
                with pytest.raises(SystemExit) as exc_info:
                    main()

            assert exc_info.value.code == 0

    def test_main_handles_exception(self):
        """Test that main handles exceptions and exits with code 1."""
        with patch("asyncio.run", side_effect=Exception("Test error")):
            with patch("gobby.runner.run_gobby") as mock_run_gobby:
                mock_run_gobby.return_value = None
                with pytest.raises(SystemExit) as exc_info:
                    main()

            assert exc_info.value.code == 1
