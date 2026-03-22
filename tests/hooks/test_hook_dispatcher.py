"""Tests for hook_dispatcher.py fail-closed behavior on critical hooks."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The dispatcher lives outside the package tree — import via path manipulation
sys.path.insert(
    0,
    str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "src"
        / "gobby"
        / "install"
        / "shared"
        / "hooks"
    ),
)

import hook_dispatcher  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────

CLAUDE_CONFIG = hook_dispatcher.CLI_CONFIGS["claude"]


@pytest.fixture()
def _patch_daemon_running():
    """Assume daemon is running for all tests."""
    with patch.object(hook_dispatcher, "check_daemon_running", new_callable=AsyncMock, return_value=True):
        yield


@pytest.fixture()
def _patch_stdin():
    """Provide valid JSON on stdin."""
    with patch("sys.stdin", StringIO('{"prompt": "test"}')):
        yield


@pytest.fixture()
def _patch_args():
    """Patch argument parsing to return a stop hook for claude."""
    args = MagicMock()
    args.type = "stop"
    args.debug = False
    args.cli = "claude"
    with patch.object(hook_dispatcher, "parse_arguments", return_value=args):
        with patch.object(hook_dispatcher, "detect_cli", return_value=CLAUDE_CONFIG):
            yield args


# ── Tests ────────────────────────────────────────────────────────────────


class TestFailClosedOnCriticalHooks:
    """Critical hooks (stop, session-start, etc.) must return exit code 2 on errors."""

    @pytest.mark.asyncio
    async def test_daemon_http_error_blocks_critical_hook(
        self, _patch_daemon_running, _patch_stdin, _patch_args
    ) -> None:
        """Daemon returns 500 on a stop hook → exit code 2 (block)."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(hook_dispatcher, "get_daemon_url", new_callable=AsyncMock, return_value="http://localhost:60887"):
                exit_code = await hook_dispatcher.main()

        assert exit_code == 2, f"Critical hook error should block (exit 2), got {exit_code}"

    @pytest.mark.asyncio
    async def test_daemon_http_error_allows_non_critical_hook(
        self, _patch_daemon_running, _patch_stdin
    ) -> None:
        """Daemon returns 500 on a non-critical hook → exit code 1 (allow)."""
        args = MagicMock()
        args.type = "post-tool-use"  # Not in critical_hooks
        args.debug = False
        args.cli = "claude"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(hook_dispatcher, "parse_arguments", return_value=args):
            with patch.object(hook_dispatcher, "detect_cli", return_value=CLAUDE_CONFIG):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    with patch.object(hook_dispatcher, "get_daemon_url", new_callable=AsyncMock, return_value="http://localhost:60887"):
                        exit_code = await hook_dispatcher.main()

        assert exit_code == 1, f"Non-critical hook error should allow (exit 1), got {exit_code}"

    @pytest.mark.asyncio
    async def test_connect_error_blocks_critical_hook(
        self, _patch_daemon_running, _patch_stdin, _patch_args
    ) -> None:
        """httpx.ConnectError on a stop hook → exit code 2."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(hook_dispatcher, "get_daemon_url", new_callable=AsyncMock, return_value="http://localhost:60887"):
                exit_code = await hook_dispatcher.main()

        assert exit_code == 2

    @pytest.mark.asyncio
    async def test_timeout_blocks_critical_hook(
        self, _patch_daemon_running, _patch_stdin, _patch_args
    ) -> None:
        """httpx.TimeoutException on a stop hook → exit code 2."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(hook_dispatcher, "get_daemon_url", new_callable=AsyncMock, return_value="http://localhost:60887"):
                exit_code = await hook_dispatcher.main()

        assert exit_code == 2

    @pytest.mark.asyncio
    async def test_generic_exception_blocks_critical_hook(
        self, _patch_daemon_running, _patch_stdin, _patch_args
    ) -> None:
        """Generic exception on a stop hook → exit code 2."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("unexpected"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(hook_dispatcher, "get_daemon_url", new_callable=AsyncMock, return_value="http://localhost:60887"):
                exit_code = await hook_dispatcher.main()

        assert exit_code == 2

    @pytest.mark.asyncio
    async def test_successful_block_still_works(
        self, _patch_daemon_running, _patch_stdin, _patch_args
    ) -> None:
        """Normal block response from daemon → exit code 2."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "decision": "block",
            "reason": "Task still in_progress",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(hook_dispatcher, "get_daemon_url", new_callable=AsyncMock, return_value="http://localhost:60887"):
                exit_code = await hook_dispatcher.main()

        assert exit_code == 2

    @pytest.mark.asyncio
    async def test_successful_allow_still_works(
        self, _patch_daemon_running, _patch_stdin, _patch_args
    ) -> None:
        """Normal allow response from daemon → exit code 0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "decision": "approve",
            "continue": True,
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(hook_dispatcher, "get_daemon_url", new_callable=AsyncMock, return_value="http://localhost:60887"):
                exit_code = await hook_dispatcher.main()

        assert exit_code == 0
