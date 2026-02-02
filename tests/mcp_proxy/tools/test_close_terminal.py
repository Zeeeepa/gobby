"""Tests for close_terminal tool."""

from unittest.mock import MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.workflows._terminal import close_terminal
from gobby.storage.sessions import Session


class TestCloseTerminalPIDResolution:
    """Tests for terminal PID resolution from session context."""

    @pytest.mark.asyncio
    async def test_resolves_pid_from_session_terminal_context(self) -> None:
        """close_terminal should resolve PID from session.terminal_context.parent_pid."""
        # Create mock session with terminal_context
        mock_session = MagicMock(spec=Session)
        mock_session.terminal_context = {"parent_pid": 12345}

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = mock_session

        with (
            patch(
                "gobby.mcp_proxy.tools.workflows._resolution.resolve_session_id"
            ) as mock_resolve,
            patch("subprocess.Popen") as mock_popen,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="# VERSION: 3.0.0\n"),
        ):
            mock_resolve.return_value = "uuid-123"

            result = await close_terminal(
                session_id="#760",
                session_manager=mock_session_manager,
                signal="TERM",
            )

            assert result["success"] is True
            assert result["target_pid"] == 12345
            assert result["pid_source"] == "session_terminal_context"

            # Verify PID was passed to script
            call_args = mock_popen.call_args
            script_args = call_args[0][0]  # First positional arg is the command list
            assert "12345" in script_args

    @pytest.mark.asyncio
    async def test_falls_back_to_ppid_discovery_when_no_session(self) -> None:
        """close_terminal should fall back to PPID discovery when no session_id provided."""
        with (
            patch("subprocess.Popen") as mock_popen,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="# VERSION: 3.0.0\n"),
        ):
            result = await close_terminal(signal="TERM")

            assert result["success"] is True
            assert result["pid_source"] == "ppid_discovery"
            assert "target_pid" not in result

            # Verify empty string passed as PID arg (script will discover via PPID)
            call_args = mock_popen.call_args
            script_args = call_args[0][0]
            # Second arg (index 1) should be empty string for PID
            assert script_args[1] == ""

    @pytest.mark.asyncio
    async def test_falls_back_when_session_has_no_terminal_context(self) -> None:
        """close_terminal should fall back when session exists but has no terminal_context."""
        mock_session = MagicMock(spec=Session)
        mock_session.terminal_context = None

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = mock_session

        with (
            patch(
                "gobby.mcp_proxy.tools.workflows._resolution.resolve_session_id"
            ) as mock_resolve,
            patch("subprocess.Popen"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="# VERSION: 3.0.0\n"),
        ):
            mock_resolve.return_value = "uuid-123"

            result = await close_terminal(
                session_id="#760",
                session_manager=mock_session_manager,
            )

            assert result["success"] is True
            assert result["pid_source"] == "ppid_discovery"

    @pytest.mark.asyncio
    async def test_falls_back_when_terminal_context_missing_parent_pid(self) -> None:
        """close_terminal should fall back when terminal_context has no parent_pid."""
        mock_session = MagicMock(spec=Session)
        mock_session.terminal_context = {"terminal": "ghostty"}  # No parent_pid

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = mock_session

        with (
            patch(
                "gobby.mcp_proxy.tools.workflows._resolution.resolve_session_id"
            ) as mock_resolve,
            patch("subprocess.Popen"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="# VERSION: 3.0.0\n"),
        ):
            mock_resolve.return_value = "uuid-123"

            result = await close_terminal(
                session_id="#760",
                session_manager=mock_session_manager,
            )

            assert result["success"] is True
            assert result["pid_source"] == "ppid_discovery"

    @pytest.mark.asyncio
    async def test_handles_session_resolution_error_gracefully(self) -> None:
        """close_terminal should handle session resolution errors gracefully."""
        mock_session_manager = MagicMock()

        with (
            patch(
                "gobby.mcp_proxy.tools.workflows._resolution.resolve_session_id"
            ) as mock_resolve,
            patch("subprocess.Popen"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="# VERSION: 3.0.0\n"),
        ):
            mock_resolve.side_effect = Exception("Session not found")

            result = await close_terminal(
                session_id="#999",
                session_manager=mock_session_manager,
            )

            # Should still succeed, falling back to PPID discovery
            assert result["success"] is True
            assert result["pid_source"] == "ppid_discovery"
