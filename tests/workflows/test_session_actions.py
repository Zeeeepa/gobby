"""Tests for workflows/session_actions.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# --- mark_session_status ---


def test_mark_session_status_current() -> None:
    from gobby.workflows.session_actions import mark_session_status

    mgr = MagicMock()
    result = mark_session_status(mgr, "sess-1", status="active")
    assert result["status_updated"] is True
    assert result["session_id"] == "sess-1"
    assert result["status"] == "active"
    mgr.update_status.assert_called_once_with("sess-1", "active")


def test_mark_session_status_no_status() -> None:
    from gobby.workflows.session_actions import mark_session_status

    result = mark_session_status(MagicMock(), "sess-1", status=None)
    assert result == {"error": "Missing status"}


def test_mark_session_status_parent() -> None:
    from gobby.workflows.session_actions import mark_session_status

    mgr = MagicMock()
    session = MagicMock()
    session.parent_session_id = "parent-1"
    mgr.get.return_value = session

    result = mark_session_status(mgr, "sess-1", status="expired", target="parent_session")
    assert result["session_id"] == "parent-1"
    mgr.update_status.assert_called_once_with("parent-1", "expired")


def test_mark_session_status_parent_not_found() -> None:
    from gobby.workflows.session_actions import mark_session_status

    mgr = MagicMock()
    mgr.get.return_value = None

    result = mark_session_status(mgr, "sess-1", status="x", target="parent_session")
    assert result == {"error": "No parent session linked"}


def test_mark_session_status_parent_no_parent_id() -> None:
    from gobby.workflows.session_actions import mark_session_status

    mgr = MagicMock()
    session = MagicMock()
    session.parent_session_id = None
    mgr.get.return_value = session

    result = mark_session_status(mgr, "sess-1", status="x", target="parent_session")
    assert result == {"error": "No parent session linked"}


# --- switch_mode ---


def test_switch_mode() -> None:
    from gobby.workflows.session_actions import switch_mode

    result = switch_mode("PLAN")
    assert "inject_context" in result
    assert "PLAN" in result["inject_context"]
    assert result["mode_switch"] == "PLAN"


def test_switch_mode_no_mode() -> None:
    from gobby.workflows.session_actions import switch_mode

    result = switch_mode(None)
    assert result == {"error": "Missing mode"}


# --- start_new_session ---


def test_start_new_session_success() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    session = MagicMock()
    session.source = "claude"
    session.project_path = "/tmp/test"
    mgr.get.return_value = session

    with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 12345
        result = start_new_session(mgr, "sess-1")

    assert result["started_new_session"] is True
    assert result["pid"] == 12345
    args, kwargs = mock_popen.call_args
    assert args[0] == ["claude"]
    assert kwargs["cwd"] == "/tmp/test"


def test_start_new_session_not_found() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    mgr.get.return_value = None
    result = start_new_session(mgr, "sess-1")
    assert result == {"error": "Session not found"}


def test_start_new_session_gemini_source() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    session = MagicMock()
    session.source = "gemini"
    session.project_path = "/tmp"
    mgr.get.return_value = session

    with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 99
        result = start_new_session(mgr, "sess-1")

    assert result["started_new_session"] is True


def test_start_new_session_antigravity_source() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    session = MagicMock()
    session.source = "antigravity"
    session.project_path = "/tmp"
    mgr.get.return_value = session

    with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 42
        result = start_new_session(mgr, "sess-1")

    assert result["started_new_session"] is True


def test_start_new_session_custom_command_and_args() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    session = MagicMock()
    session.project_path = "/tmp"
    mgr.get.return_value = session

    with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 1
        result = start_new_session(mgr, "s1", command="claude", args="--help -v")

    assert result["started_new_session"] is True


def test_start_new_session_list_args() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    session = MagicMock()
    session.project_path = "/tmp"
    mgr.get.return_value = session

    with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 1
        result = start_new_session(mgr, "s1", command="claude", args=["--help"])

    assert result["started_new_session"] is True


def test_start_new_session_with_prompt() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    session = MagicMock()
    session.project_path = "/tmp"
    mgr.get.return_value = session

    with patch("gobby.workflows.session_actions.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 1
        result = start_new_session(mgr, "s1", prompt="do something")

    assert result["started_new_session"] is True


def test_start_new_session_error() -> None:
    from gobby.workflows.session_actions import start_new_session

    mgr = MagicMock()
    session = MagicMock()
    session.project_path = "/tmp"
    mgr.get.return_value = session

    with patch("gobby.workflows.session_actions.subprocess.Popen", side_effect=OSError("not found")):
        result = start_new_session(mgr, "s1")

    assert "error" in result
