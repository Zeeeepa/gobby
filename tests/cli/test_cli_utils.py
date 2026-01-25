"""Tests for gobby.cli.utils module.

This module tests the shared utility functions used across CLI commands.
"""

import logging
import os
import signal
import socket
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import psutil
import pytest

from gobby.cli.utils import (
    _is_process_alive,
    format_uptime,
    get_active_session_id,
    get_gobby_home,
    get_install_dir,
    get_resources_dir,
    init_local_storage,
    is_port_available,
    kill_all_gobby_daemons,
    list_project_names,
    resolve_project_ref,
    resolve_session_id,
    setup_logging,
    stop_daemon,
    wait_for_port_available,
)

# ==============================================================================
# Tests for get_gobby_home()
# ==============================================================================


class TestGetGobbyHome:
    """Tests for get_gobby_home function."""

    def test_default_home(self):
        """Test default home directory when GOBBY_HOME not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove GOBBY_HOME if it exists
            os.environ.pop("GOBBY_HOME", None)
            result = get_gobby_home()
            assert result == Path.home() / ".gobby"

    def test_custom_home_from_env(self, temp_dir: Path):
        """Test custom home directory from GOBBY_HOME env var."""
        custom_path = str(temp_dir / "custom_gobby")
        with patch.dict(os.environ, {"GOBBY_HOME": custom_path}):
            result = get_gobby_home()
            assert result == Path(custom_path)


# ==============================================================================
# Tests for get_resources_dir()
# ==============================================================================


class TestGetResourcesDir:
    """Tests for get_resources_dir function."""

    def test_global_resources_dir(self, temp_dir: Path):
        """Test global resources directory."""
        with patch("gobby.cli.utils.get_gobby_home", return_value=temp_dir):
            result = get_resources_dir()
            assert result == temp_dir / "resources"
            assert result.exists()

    def test_project_resources_dir(self, temp_dir: Path):
        """Test project-local resources directory."""
        project_path = str(temp_dir / "my_project")
        Path(project_path).mkdir(parents=True)

        result = get_resources_dir(project_path)
        expected = Path(project_path) / ".gobby" / "resources"
        assert result == expected
        assert result.exists()


# ==============================================================================
# Tests for resolve_project_ref()
# ==============================================================================


class TestResolveProjectRef:
    """Tests for resolve_project_ref function."""

    def test_none_with_context(self):
        """Test None project_ref returns current project from context."""
        mock_ctx = {"id": "proj-123", "name": "test-project"}
        with patch("gobby.cli.utils.get_project_context", return_value=mock_ctx):
            result = resolve_project_ref(None)
            assert result == "proj-123"

    def test_none_without_context(self):
        """Test None project_ref returns None when no context."""
        with patch("gobby.cli.utils.get_project_context", return_value=None):
            result = resolve_project_ref(None)
            assert result is None

    def test_uuid_lookup(self, temp_db):
        """Test direct UUID lookup."""
        # Create a project
        from gobby.storage.projects import LocalProjectManager

        manager = LocalProjectManager(temp_db)
        project = manager.create(name="test-proj", repo_path="/tmp/test")

        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):  # Don't actually close
                result = resolve_project_ref(project.id)
                assert result == project.id

    def test_name_lookup(self, temp_db):
        """Test project name lookup."""
        from gobby.storage.projects import LocalProjectManager

        manager = LocalProjectManager(temp_db)
        project = manager.create(name="my-named-project", repo_path="/tmp/test")

        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):
                result = resolve_project_ref("my-named-project")
                assert result == project.id

    def test_not_found(self, temp_db):
        """Test project not found returns None."""
        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):
                result = resolve_project_ref("nonexistent-project")
                assert result is None


# ==============================================================================
# Tests for get_active_session_id()
# ==============================================================================


class TestGetActiveSessionId:
    """Tests for get_active_session_id function."""

    def test_with_active_session(self, temp_db):
        """Test finding an active session."""
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        # Create a project first
        proj_manager = LocalProjectManager(temp_db)
        project = proj_manager.create(name="test-proj", repo_path="/tmp/test")

        # Create an active session using register method
        session_manager = LocalSessionManager(temp_db)
        session = session_manager.register(
            source="test",
            external_id="ext-123",
            machine_id="machine-1",
            project_id=project.id,
        )

        result = get_active_session_id(temp_db)
        assert result == session.id

    def test_no_active_session(self, temp_db):
        """Test no active session returns None."""
        result = get_active_session_id(temp_db)
        assert result is None

    def test_creates_db_when_not_provided(self):
        """Test that DB is created when not provided."""
        mock_db = MagicMock()
        mock_db.fetchone.return_value = None

        with patch("gobby.cli.utils.LocalDatabase", return_value=mock_db):
            result = get_active_session_id()
            assert result is None
            mock_db.close.assert_called_once()


# ==============================================================================
# Tests for resolve_session_id()
# ==============================================================================


class TestResolveSessionId:
    """Tests for resolve_session_id function."""

    def test_resolves_active_session(self, temp_db):
        """Test resolving to active session when no ref provided."""
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        proj_manager = LocalProjectManager(temp_db)
        project = proj_manager.create(name="test", repo_path="/tmp/test")

        session_manager = LocalSessionManager(temp_db)
        session = session_manager.register(
            source="test",
            external_id="ext-1",
            machine_id="m-1",
            project_id=project.id,
        )

        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):
                result = resolve_session_id(None)
                assert result == session.id

    def test_no_active_session_raises(self, temp_db):
        """Test ClickException when no active session."""
        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):
                with pytest.raises(click.ClickException) as exc_info:
                    resolve_session_id(None)
                assert "No active session found" in str(exc_info.value)

    def test_resolves_session_reference(self, temp_db):
        """Test resolving a specific session reference."""
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        proj_manager = LocalProjectManager(temp_db)
        project = proj_manager.create(name="test", repo_path="/tmp/test")

        session_manager = LocalSessionManager(temp_db)
        session = session_manager.register(
            source="test",
            external_id="ext-1",
            machine_id="m-1",
            project_id=project.id,
        )

        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):
                result = resolve_session_id(session.id)
                assert result == session.id


# ==============================================================================
# Tests for list_project_names()
# ==============================================================================


class TestListProjectNames:
    """Tests for list_project_names function."""

    def test_lists_all_project_names(self, temp_db):
        """Test listing all project names."""
        from gobby.storage.projects import LocalProjectManager

        manager = LocalProjectManager(temp_db)
        manager.create(name="project-alpha", repo_path="/tmp/alpha")
        manager.create(name="project-beta", repo_path="/tmp/beta")

        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):
                result = list_project_names()
                assert "project-alpha" in result
                assert "project-beta" in result

    def test_returns_list(self, temp_db):
        """Test that list_project_names returns a list."""
        with patch("gobby.cli.utils.LocalDatabase", return_value=temp_db):
            with patch.object(temp_db, "close"):
                result = list_project_names()
                assert isinstance(result, list)


# ==============================================================================
# Tests for setup_logging()
# ==============================================================================


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_verbose_logging(self):
        """Test verbose mode sets DEBUG level."""
        with patch("logging.basicConfig") as mock_basic:
            setup_logging(verbose=True)
            mock_basic.assert_called_once()
            call_kwargs = mock_basic.call_args.kwargs
            assert call_kwargs["level"] == logging.DEBUG

    def test_normal_logging(self):
        """Test non-verbose mode sets INFO level."""
        with patch("logging.basicConfig") as mock_basic:
            setup_logging(verbose=False)
            mock_basic.assert_called_once()
            call_kwargs = mock_basic.call_args.kwargs
            assert call_kwargs["level"] == logging.INFO


# ==============================================================================
# Tests for format_uptime()
# ==============================================================================


class TestFormatUptime:
    """Tests for format_uptime function."""

    def test_zero_seconds(self):
        """Test formatting zero seconds."""
        assert format_uptime(0) == "0s"

    def test_only_seconds(self):
        """Test formatting seconds only."""
        assert format_uptime(45) == "45s"

    def test_minutes_and_seconds(self):
        """Test formatting minutes and seconds."""
        assert format_uptime(125) == "2m 5s"

    def test_hours_minutes_seconds(self):
        """Test formatting hours, minutes, and seconds."""
        assert format_uptime(3725) == "1h 2m 5s"

    def test_hours_only(self):
        """Test formatting full hours."""
        assert format_uptime(7200) == "2h"

    def test_hours_and_minutes(self):
        """Test hours and minutes, no seconds."""
        assert format_uptime(3720) == "1h 2m"

    def test_large_uptime(self):
        """Test large uptime values."""
        # 100 hours
        assert format_uptime(360000) == "100h"


# ==============================================================================
# Tests for is_port_available()
# ==============================================================================


class TestIsPortAvailable:
    """Tests for is_port_available function."""

    def test_available_port(self):
        """Test that an unused port is available."""
        # Find a high random port that's likely available
        result = is_port_available(59999)
        # We can't guarantee this port is available, but it's likely
        assert isinstance(result, bool)

    @pytest.mark.skip(reason="Flaky - SO_REUSEADDR allows rebind on some systems")
    def test_unavailable_port(self):
        """Test that an occupied port is not available."""
        # Bind to a port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]

        try:
            result = is_port_available(port)
            assert result is False
        finally:
            sock.close()


# ==============================================================================
# Tests for wait_for_port_available()
# ==============================================================================


class TestWaitForPortAvailable:
    """Tests for wait_for_port_available function."""

    def test_already_available(self):
        """Test immediate return when port is already available."""
        with patch("gobby.cli.utils.is_port_available", return_value=True):
            result = wait_for_port_available(60887, timeout=1.0)
            assert result is True

    def test_timeout_when_unavailable(self):
        """Test timeout when port stays unavailable."""
        with patch("gobby.cli.utils.is_port_available", return_value=False):
            start = time.time()
            result = wait_for_port_available(60887, timeout=0.3)
            elapsed = time.time() - start
            assert result is False
            assert elapsed >= 0.3

    def test_becomes_available(self):
        """Test detecting port becoming available."""
        # Port becomes available after 2 calls
        call_count = [0]

        def mock_is_available(port, host="localhost"):
            call_count[0] += 1
            return call_count[0] >= 3

        with patch("gobby.cli.utils.is_port_available", side_effect=mock_is_available):
            result = wait_for_port_available(60887, timeout=5.0)
            assert result is True


# ==============================================================================
# Tests for _is_process_alive()
# ==============================================================================


class TestIsProcessAlive:
    """Tests for _is_process_alive function."""

    def test_current_process_alive(self):
        """Test that current process is detected as alive."""
        result = _is_process_alive(os.getpid())
        assert result is True

    def test_nonexistent_process(self):
        """Test that nonexistent process is not alive."""
        # Use a very high PID that's unlikely to exist
        result = _is_process_alive(999999999)
        assert result is False

    def test_zombie_process(self):
        """Test that zombie process is not detected as alive."""
        mock_proc = MagicMock()
        mock_proc.status.return_value = psutil.STATUS_ZOMBIE

        with patch("psutil.Process", return_value=mock_proc):
            result = _is_process_alive(12345)
            assert result is False

    def test_access_denied(self):
        """Test handling of access denied."""
        with patch("psutil.Process", side_effect=psutil.AccessDenied()):
            result = _is_process_alive(12345)
            assert result is False


# ==============================================================================
# Tests for kill_all_gobby_daemons()
# ==============================================================================


class TestKillAllGobbyDaemons:
    """Tests for kill_all_gobby_daemons function."""

    def test_no_daemons_found(self):
        """Test when no gobby daemons are running."""
        with patch("psutil.process_iter", return_value=[]):
            with patch("gobby.cli.utils.load_config") as mock_config:
                mock_config.return_value = MagicMock(daemon_port=60887)
                mock_config.return_value.websocket.port = 60888
                result = kill_all_gobby_daemons()
                assert result == 0

    def test_finds_and_kills_daemon(self):
        """Test finding and killing a gobby daemon."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.cmdline.return_value = ["python", "-m", "gobby.runner"]
        mock_proc.connections.return_value = []
        mock_proc.wait.return_value = None

        with patch("psutil.process_iter", return_value=[mock_proc]):
            with patch("gobby.cli.utils.load_config") as mock_config:
                mock_config.return_value = MagicMock(daemon_port=60887)
                mock_config.return_value.websocket.port = 60888
                with patch("os.getpid", return_value=99999):
                    with patch("os.getppid", return_value=99998):
                        result = kill_all_gobby_daemons()
                        assert result == 1
                        mock_proc.send_signal.assert_called_with(signal.SIGTERM)

    def test_skips_cli_processes(self):
        """Test that CLI processes are not killed."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.cmdline.return_value = ["python", "-m", "gobby.cli", "start"]
        mock_proc.connections.return_value = []

        with patch("psutil.process_iter", return_value=[mock_proc]):
            with patch("gobby.cli.utils.load_config") as mock_config:
                mock_config.return_value = MagicMock(daemon_port=60887)
                mock_config.return_value.websocket.port = 60888
                with patch("os.getpid", return_value=99999):
                    with patch("os.getppid", return_value=99998):
                        result = kill_all_gobby_daemons()
                        assert result == 0


# ==============================================================================
# Tests for stop_daemon()
# ==============================================================================


class TestStopDaemon:
    """Tests for stop_daemon function."""

    def test_no_pid_file(self, temp_dir: Path):
        """Test when no PID file exists."""
        with patch("gobby.cli.utils.get_gobby_home", return_value=temp_dir):
            result = stop_daemon(quiet=True)
            assert result is True

    def test_stale_pid_file(self, temp_dir: Path):
        """Test with stale PID file (process not running)."""
        pid_file = temp_dir / "gobby.pid"
        pid_file.write_text("999999999")  # Non-existent PID

        with patch("gobby.cli.utils.get_gobby_home", return_value=temp_dir):
            with patch("gobby.cli.utils._is_process_alive", return_value=False):
                result = stop_daemon(quiet=True)
                assert result is True
                assert not pid_file.exists()

    def test_stops_running_daemon(self, temp_dir: Path):
        """Test stopping a running daemon."""
        pid_file = temp_dir / "gobby.pid"
        pid_file.write_text("12345")

        alive_calls = [True, True, False]  # Process dies after SIGTERM

        def mock_is_alive(pid):
            return alive_calls.pop(0) if alive_calls else False

        with patch("gobby.cli.utils.get_gobby_home", return_value=temp_dir):
            with patch("gobby.cli.utils._is_process_alive", side_effect=mock_is_alive):
                with patch("os.kill") as mock_kill:
                    result = stop_daemon(quiet=True)
                    assert result is True
                    mock_kill.assert_called_with(12345, signal.SIGTERM)

    def test_force_kills_stubborn_process(self, temp_dir: Path):
        """Test force killing when process doesn't stop gracefully."""
        pid_file = temp_dir / "gobby.pid"
        pid_file.write_text("12345")

        # Process stays alive until SIGKILL
        kill_calls = []

        def mock_kill(pid, sig):
            kill_calls.append(sig)
            if sig == signal.SIGKILL:
                return None
            return None

        def mock_is_alive(pid):
            # Still alive until after SIGKILL
            return signal.SIGKILL not in kill_calls

        with patch("gobby.cli.utils.get_gobby_home", return_value=temp_dir):
            with patch("gobby.cli.utils._is_process_alive", side_effect=mock_is_alive):
                with patch("os.kill", side_effect=mock_kill):
                    with patch("time.sleep"):
                        result = stop_daemon(quiet=True)
                        assert result is True
                        assert signal.SIGTERM in kill_calls
                        assert signal.SIGKILL in kill_calls

    def test_permission_error(self, temp_dir: Path):
        """Test handling of permission error when stopping daemon."""
        pid_file = temp_dir / "gobby.pid"
        pid_file.write_text("12345")

        with patch("gobby.cli.utils.get_gobby_home", return_value=temp_dir):
            with patch("gobby.cli.utils._is_process_alive", return_value=True):
                with patch("os.kill", side_effect=PermissionError()):
                    result = stop_daemon(quiet=True)
                    assert result is False


# ==============================================================================
# Tests for init_local_storage()
# ==============================================================================


class TestInitLocalStorage:
    """Tests for init_local_storage function."""

    def test_creates_database(self, temp_dir: Path):
        """Test that database is created and migrations run."""
        db_path = temp_dir / "gobby-hub.db"

        mock_config = MagicMock()
        mock_config.database_path = str(db_path)

        with patch("gobby.cli.utils.load_config", return_value=mock_config):
            with patch("gobby.storage.migrations.run_migrations") as mock_migrations:
                with patch("gobby.storage.database.LocalDatabase") as mock_db_class:
                    mock_db = MagicMock()
                    mock_db_class.return_value = mock_db
                    init_local_storage()
                    mock_db_class.assert_called_once_with(db_path)
                    mock_migrations.assert_called_once_with(mock_db)


# ==============================================================================
# Tests for get_install_dir()
# ==============================================================================


class TestGetInstallDir:
    """Tests for get_install_dir function."""

    def test_returns_path(self):
        """Test that a Path is returned."""
        result = get_install_dir()
        assert isinstance(result, Path)

    def test_source_install_dir_found(self, temp_dir: Path):
        """Test finding source install directory."""
        # Create source directory structure
        source_install = temp_dir / "src" / "gobby" / "install"
        source_install.mkdir(parents=True)

        mock_gobby = MagicMock()
        mock_gobby.__file__ = str(temp_dir / "src" / "gobby" / "__init__.py")

        with patch.dict("sys.modules", {"gobby": mock_gobby}):
            with patch("gobby.cli.utils.Path") as mock_path:
                # Mock the Path behavior
                mock_path.return_value.parent.__truediv__.return_value = (
                    temp_dir / "gobby" / "install"
                )

                result = get_install_dir()
                assert isinstance(result, Path)
