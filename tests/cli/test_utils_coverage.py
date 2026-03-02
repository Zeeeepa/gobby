"""Tests for cli/utils.py — targeting uncovered lines."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# --- get_gobby_home ---


def test_get_gobby_home_default() -> None:
    from gobby.cli.utils import get_gobby_home

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOBBY_HOME", None)
        result = get_gobby_home()
        assert result == Path.home() / ".gobby"


def test_get_gobby_home_custom() -> None:
    from gobby.cli.utils import get_gobby_home

    with patch.dict(os.environ, {"GOBBY_HOME": "/custom/path"}):
        result = get_gobby_home()
        assert result == Path("/custom/path")


# --- get_resources_dir ---


def test_get_resources_dir_global(tmp_path: Path) -> None:
    from gobby.cli.utils import get_resources_dir

    with patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path):
        result = get_resources_dir()
        assert result == tmp_path / "resources"
        assert result.exists()


def test_get_resources_dir_project(tmp_path: Path) -> None:
    from gobby.cli.utils import get_resources_dir

    result = get_resources_dir(str(tmp_path))
    assert result == tmp_path / ".gobby" / "resources"
    assert result.exists()


# --- format_uptime ---


def test_format_uptime_seconds() -> None:
    from gobby.cli.utils import format_uptime

    assert format_uptime(45) == "45s"
    assert format_uptime(0) == "0s"


def test_format_uptime_minutes() -> None:
    from gobby.cli.utils import format_uptime

    assert format_uptime(125) == "2m 5s"
    assert format_uptime(60) == "1m"


def test_format_uptime_hours() -> None:
    from gobby.cli.utils import format_uptime

    assert format_uptime(3661) == "1h 1m 1s"
    assert format_uptime(7200) == "2h"


# --- find_web_dir ---


def test_find_web_dir_from_config(tmp_path: Path) -> None:
    from gobby.cli.utils import find_web_dir

    web_dir = tmp_path / "my-web"
    web_dir.mkdir()
    (web_dir / "package.json").write_text("{}")

    config = MagicMock()
    config.ui.web_dir = str(web_dir)

    result = find_web_dir(config)
    assert result == web_dir


def test_find_web_dir_config_missing(tmp_path: Path) -> None:
    from gobby.cli.utils import find_web_dir

    config = MagicMock()
    config.ui.web_dir = str(tmp_path / "nonexistent")

    # Also patch cwd to avoid matching real cwd
    with patch("gobby.cli.utils.Path.cwd", return_value=tmp_path):
        result = find_web_dir(config)
    assert result is None


def test_find_web_dir_from_cwd(tmp_path: Path) -> None:
    from gobby.cli.utils import find_web_dir

    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "package.json").write_text("{}")

    with patch("gobby.cli.utils.Path.cwd", return_value=tmp_path):
        result = find_web_dir(None)
    assert result == web_dir


def test_find_web_dir_none(tmp_path: Path) -> None:
    from gobby.cli.utils import find_web_dir

    with patch("gobby.cli.utils.Path.cwd", return_value=tmp_path):
        result = find_web_dir(None)
    assert result is None


# --- is_port_available ---


def test_is_port_available() -> None:
    from gobby.cli.utils import is_port_available

    # Port 0 always available (OS assigns random)
    # Test with a very high port that's likely available
    result = is_port_available(0, "127.0.0.1")
    assert result is True


# --- stop_watchdog ---


def test_stop_watchdog_no_pid_file(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_watchdog

    with patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path):
        result = stop_watchdog(quiet=True)
    assert result is True


def test_stop_watchdog_stale_pid(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_watchdog

    pid_file = tmp_path / "watchdog.pid"
    pid_file.write_text("999999")

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils._is_process_alive", return_value=False),
    ):
        result = stop_watchdog(quiet=False)
    assert result is True
    assert not pid_file.exists()


def test_stop_watchdog_bad_pid_file(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_watchdog

    pid_file = tmp_path / "watchdog.pid"
    pid_file.write_text("not-a-number")

    with patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path):
        result = stop_watchdog(quiet=False)
    assert result is True


# --- stop_ui_server ---


def test_stop_ui_server_no_pid_file(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_ui_server

    with patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path):
        result = stop_ui_server(quiet=True)
    assert result is True


def test_stop_ui_server_stale_pid(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_ui_server

    pid_file = tmp_path / "ui.pid"
    pid_file.write_text("999999")

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils._is_process_alive", return_value=False),
    ):
        result = stop_ui_server(quiet=False)
    assert result is True


# --- stop_daemon ---


def test_stop_daemon_no_pid_file(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_daemon

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils.stop_ui_server"),
        patch("gobby.cli.utils.stop_watchdog"),
    ):
        result = stop_daemon(quiet=True)
    assert result is True


def test_stop_daemon_stale_pid(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_daemon

    pid_file = tmp_path / "gobby.pid"
    pid_file.write_text("999999")

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils.stop_ui_server"),
        patch("gobby.cli.utils.stop_watchdog"),
        patch("gobby.cli.utils._is_process_alive", return_value=False),
        patch("gobby.cli.utils.kill_all_gobby_daemons", return_value=0),
    ):
        result = stop_daemon(quiet=False)
    assert result is True


def test_stop_daemon_bad_pid_file(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_daemon

    pid_file = tmp_path / "gobby.pid"
    pid_file.write_text("not-a-pid")

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils.stop_ui_server"),
        patch("gobby.cli.utils.stop_watchdog"),
    ):
        result = stop_daemon(quiet=False)
    assert result is False


def test_stop_daemon_not_gobby_process(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_daemon

    pid_file = tmp_path / "gobby.pid"
    pid_file.write_text("12345")

    mock_proc = MagicMock()
    mock_proc.cmdline.return_value = ["node", "server.js"]

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils.stop_ui_server"),
        patch("gobby.cli.utils.stop_watchdog"),
        patch("gobby.cli.utils._is_process_alive", return_value=True),
        patch("gobby.cli.utils.psutil.Process", return_value=mock_proc),
        patch("gobby.cli.utils.kill_all_gobby_daemons", return_value=0),
    ):
        result = stop_daemon(quiet=False)
    assert result is True


def test_stop_daemon_process_lookup_error(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_daemon

    pid_file = tmp_path / "gobby.pid"
    pid_file.write_text("12345")

    mock_proc = MagicMock()
    mock_proc.cmdline.return_value = ["python", "-m", "gobby.runner"]

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils.stop_ui_server"),
        patch("gobby.cli.utils.stop_watchdog"),
        patch("gobby.cli.utils._is_process_alive", return_value=True),
        patch("gobby.cli.utils.psutil.Process", return_value=mock_proc),
        patch("gobby.cli.utils.os.kill", side_effect=ProcessLookupError),
    ):
        result = stop_daemon(quiet=False)
    assert result is True


def test_stop_daemon_permission_error(tmp_path: Path) -> None:
    from gobby.cli.utils import stop_daemon

    pid_file = tmp_path / "gobby.pid"
    pid_file.write_text("12345")

    mock_proc = MagicMock()
    mock_proc.cmdline.return_value = ["python", "-m", "gobby.runner"]

    with (
        patch("gobby.cli.utils.get_gobby_home", return_value=tmp_path),
        patch("gobby.cli.utils.stop_ui_server"),
        patch("gobby.cli.utils.stop_watchdog"),
        patch("gobby.cli.utils._is_process_alive", return_value=True),
        patch("gobby.cli.utils.psutil.Process", return_value=mock_proc),
        patch("gobby.cli.utils.os.kill", side_effect=PermissionError),
    ):
        result = stop_daemon(quiet=False)
    assert result is False


# --- load_full_config_from_db ---


def test_load_full_config_from_db_no_db(tmp_path: Path) -> None:
    from gobby.cli.utils import load_full_config_from_db

    mock_config = MagicMock()
    mock_config.database_path = str(tmp_path / "nonexistent.db")

    with patch("gobby.cli.utils.load_config", return_value=mock_config):
        result = load_full_config_from_db()
    assert result is mock_config


def test_load_full_config_from_db_with_db(tmp_path: Path) -> None:
    from gobby.cli.utils import load_full_config_from_db

    db_path = tmp_path / "test.db"
    db_path.write_bytes(b"")  # Create empty file

    mock_config = MagicMock()
    mock_config.database_path = str(db_path)

    final_config = MagicMock()

    with (
        patch("gobby.cli.utils.load_config") as mock_load,
        patch("gobby.cli.utils.LocalDatabase"),
        patch("gobby.storage.config_store.ConfigStore"),
        patch("gobby.storage.secrets.SecretStore"),
    ):
        mock_load.side_effect = [mock_config, final_config]
        result = load_full_config_from_db()
    assert result is final_config
