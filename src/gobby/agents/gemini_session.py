"""Gemini session ID capture utility.

Captures Gemini's session_id via stream-json output before launching interactive mode.
This is necessary because Gemini CLI in interactive mode cannot introspect its own
session_id, but we need it for:
1. Linking to Gobby sessions (external_id)
2. Resume functionality with `gemini -r {session_id}`
3. MCP tool calls that require session context
"""

import asyncio
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GeminiSessionInfo:
    """Captured Gemini session information."""

    session_id: str
    model: str | None = None


async def capture_gemini_session_id(
    timeout: float = 10.0,
) -> GeminiSessionInfo:
    """Capture Gemini's session_id via preflight stream-json call.

    Launches Gemini with minimal prompt in stream-json mode,
    filters through token error noise to find init JSON,
    extracts session_id, then terminates.

    Note: Gemini CLI outputs token errors to stdout (not stderr),
    so we must filter line-by-line for valid JSON.

    Args:
        timeout: Max seconds to wait for init JSON (default 10s to account
                 for auth wait time which can take ~4s)

    Returns:
        GeminiSessionInfo with captured session_id and model

    Raises:
        asyncio.TimeoutError: If init JSON not received within timeout
        ValueError: If session_id not found in output
        FileNotFoundError: If gemini CLI is not installed
    """
    logger.debug("Starting Gemini preflight to capture session_id")

    try:
        proc = await asyncio.create_subprocess_exec(
            "gemini",
            ".",
            "-o",
            "stream-json",
            "--allowed-mcp-server-names",
            "",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise FileNotFoundError(
            "Gemini CLI not found. Install with: npm install -g @google/gemini-cli"
        ) from None

    try:

        async def read_init() -> GeminiSessionInfo:
            """Read lines until we find the init JSON."""
            if proc.stdout is None:
                raise RuntimeError("Process stdout is not available")
            async for line in proc.stdout:
                text = line.decode().strip()

                # Skip non-JSON lines (token error noise)
                if not text.startswith("{"):
                    continue

                try:
                    data = json.loads(text)
                    if data.get("type") == "init":
                        session_id = data.get("session_id")
                        if not session_id:
                            raise ValueError("Init JSON missing session_id field")

                        logger.debug(
                            f"Captured Gemini session_id: {session_id}, model: {data.get('model')}"
                        )
                        return GeminiSessionInfo(
                            session_id=session_id,
                            model=data.get("model"),
                        )
                except json.JSONDecodeError:
                    # Not valid JSON, skip
                    continue

            raise ValueError("No init JSON found in Gemini output")

        return await asyncio.wait_for(read_init(), timeout=timeout)

    finally:
        # Terminate the preflight process
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()
