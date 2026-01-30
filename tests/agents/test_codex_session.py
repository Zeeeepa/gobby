import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from gobby.agents.codex_session import (
    SESSION_ID_PATTERN,
    capture_codex_session_id,
)

pytestmark = pytest.mark.unit

# Sample output matching the regex in codex_session.py
SAMPLE_CODEX_OUTPUT = """OpenAI Codex v0.80.0 (research preview)
--------
workdir: /path/to/dir
model: gpt-5.2-codex
session id: 019bbaea-3e0f-7d61-afc4-56a9456c2c7d
--------
"""


@pytest.mark.asyncio
async def test_capture_codex_session_id_success():
    """Test successful session ID capture from Codex output."""
    # Mock the process
    mock_proc = AsyncMock()
    # communicate is an async method on the subprocess object
    # It returns (stdout, stderr)
    mock_proc.communicate.return_value = (b"", SAMPLE_CODEX_OUTPUT.encode())

    # mock create_subprocess_exec to be an async function returning mock_proc
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_proc

        result = await capture_codex_session_id()

        assert result.session_id == "019bbaea-3e0f-7d61-afc4-56a9456c2c7d"
        assert result.model == "gpt-5.2-codex"
        assert result.workdir == "/path/to/dir"

        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "codex"
        assert args[1] == "exec"
        assert args[2] == "exit"


@pytest.mark.asyncio
async def test_capture_codex_session_id_no_id_found():
    """Test proper error when session ID is missing from output."""
    mock_proc = AsyncMock()
    output = "OpenAI Codex\n--------\nmodel: foo\n"
    mock_proc.communicate.return_value = (b"", output.encode())

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_proc

        with pytest.raises(ValueError, match="No session id found"):
            await capture_codex_session_id()


@pytest.mark.asyncio
async def test_capture_codex_session_id_timeout():
    """Test timeout handling when Codex hangs."""
    mock_proc = AsyncMock()
    # mock_proc.wait needs to be awaitable
    mock_proc.wait.return_value = None

    # We mock asyncio.wait_for to raise TimeoutError
    # We also need to mock create_subprocess_exec to return our proc

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_proc

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(asyncio.TimeoutError):
                await capture_codex_session_id(timeout=0.1)

            # Ensure process kill was attempted
            mock_proc.kill.assert_called_once()
            mock_proc.wait.assert_called_once()


@pytest.mark.asyncio
async def test_capture_codex_session_id_not_installed():
    """Test FileNotFoundError when codex command is missing."""
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError, match="Codex CLI not found"):
            await capture_codex_session_id()


def test_session_id_pattern_regex() -> None:
    """Test the session ID regex pattern."""
    assert (
        SESSION_ID_PATTERN.match("session id: 019bbaea-3e0f-7d61-afc4-56a9456c2c7d").group(1)
        == "019bbaea-3e0f-7d61-afc4-56a9456c2c7d"
    )
    assert SESSION_ID_PATTERN.match("Session ID: 1234-5678").group(1) == "1234-5678"
    # The regex is strict (via $), so trailing spaces cause failure.
    # The code strips lines before matching, so we test stripped strings.
    assert SESSION_ID_PATTERN.match("session id:   abcdef-1234").group(1) == "abcdef-1234"
