import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.gemini_session import capture_gemini_session_id

pytestmark = pytest.mark.unit

# Sample init JSON from Gemini CLI
SAMPLE_GEMINI_INIT_JSON = json.dumps(
    {
        "type": "init",
        "session_id": "019bbaea-3e0f-7d61-afc4-56a9456c2c7d",
        "model": "gemini-1.5-pro",
    }
)


@pytest.mark.asyncio
async def test_capture_gemini_session_id_success():
    """Test successful session ID capture from Gemini stream-json output."""
    mock_proc = MagicMock()

    # Needs to be an async iterator for "async for line in proc.stdout"
    async def output_lines():
        # Yield noise line first, then init line
        yield b"Some token error noise\n"
        yield (SAMPLE_GEMINI_INIT_JSON + "\n").encode()
        yield b'{"type": "other"}\n'

    mock_proc.stdout = output_lines()
    mock_proc.wait = MagicMock()
    mock_proc.terminate = MagicMock()

    # Mock wait as an async method
    async def async_wait():
        return

    mock_proc.wait = async_wait

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await capture_gemini_session_id()

        assert result.session_id == "019bbaea-3e0f-7d61-afc4-56a9456c2c7d"
        assert result.model == "gemini-1.5-pro"

        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "gemini"
        assert args[2] == "-o"
        assert args[3] == "stream-json"

        # Verify cleanup
        mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_capture_gemini_session_id_no_init_found():
    """Test error when init JSON is missing from output."""
    mock_proc = MagicMock()

    async def output_lines():
        yield b'{"type": "other"}\n'
        yield b'{"type": "goodbye"}\n'

    mock_proc.stdout = output_lines()

    async def async_wait():
        return

    mock_proc.wait = async_wait
    mock_proc.terminate = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(ValueError, match="No init JSON found"):
            await capture_gemini_session_id()


@pytest.mark.asyncio
async def test_capture_gemini_session_id_timeout():
    """Test timeout handling when Gemini hangs."""
    mock_proc = MagicMock()
    mock_proc.stdout = None  # Prevent reading attempt causing other errors if it got that far

    # We patch wait_for to simulate timeout
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        # The function calls asyncio.wait_for(read_init(), timeout=timeout)
        # We need to ensure that raises TimeoutError

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            # We need mock_proc.wait to be awaitable for the cleanup block
            async def async_wait():
                return

            mock_proc.wait = async_wait
            mock_proc.kill = MagicMock()
            mock_proc.terminate = MagicMock()

            with pytest.raises(asyncio.TimeoutError):
                await capture_gemini_session_id(timeout=0.1)

            # Ensure process kill was attempted in finally block
            mock_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_capture_gemini_session_id_not_installed():
    """Test FileNotFoundError when gemini command is missing."""
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError, match="Gemini CLI not found"):
            await capture_gemini_session_id()


@pytest.mark.asyncio
async def test_capture_gemini_session_id_malformed_json():
    """Test resilience against malformed JSON in output."""
    mock_proc = MagicMock()

    async def output_lines():
        yield b"{incomplete json\n"  # Should be skipped
        yield (SAMPLE_GEMINI_INIT_JSON + "\n").encode()

    mock_proc.stdout = output_lines()

    async def async_wait():
        return

    mock_proc.wait = async_wait
    mock_proc.terminate = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await capture_gemini_session_id()
        assert result.session_id == "019bbaea-3e0f-7d61-afc4-56a9456c2c7d"
