"""Codex session ID capture utility.

Captures Codex's session_id from the startup banner before launching interactive mode.
This is necessary because we need the session_id to:
1. Link to Gobby sessions (external_id)
2. Resume functionality with `codex resume {session_id}`
3. MCP tool calls that require session context
"""

import asyncio
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Regex to match "session id: {uuid}" in startup banner
SESSION_ID_PATTERN = re.compile(r"^session id:\s*([0-9a-f-]+)$", re.IGNORECASE)


@dataclass
class CodexSessionInfo:
    """Captured Codex session information."""

    session_id: str
    model: str | None = None
    workdir: str | None = None


async def capture_codex_session_id(
    timeout: float = 30.0,
) -> CodexSessionInfo:
    """Capture Codex's session_id via preflight exec call.

    Launches Codex with minimal command (`codex exec "exit"`),
    parses the startup banner for session_id, then returns.

    The Codex banner format is:
        OpenAI Codex v0.80.0 (research preview)
        --------
        workdir: /path/to/dir
        model: gpt-5.2-codex
        ...
        session id: 019bbaea-3e0f-7d61-afc4-56a9456c2c7d
        --------

    Args:
        timeout: Max seconds to wait for exec to complete (default 30s
                 to account for model loading time)

    Returns:
        CodexSessionInfo with captured session_id and metadata

    Raises:
        asyncio.TimeoutError: If exec doesn't complete within timeout
        ValueError: If session_id not found in output
        FileNotFoundError: If codex CLI is not installed
    """
    logger.debug("Starting Codex preflight to capture session_id")

    try:
        proc = await asyncio.create_subprocess_exec(
            "codex",
            "exec",
            "exit",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "Codex CLI not found. Install from: https://github.com/openai/codex"
        ) from e

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise

    # Codex outputs the startup banner (including session id) to stderr
    output = stderr.decode()
    session_id: str | None = None
    model: str | None = None
    workdir: str | None = None

    # Parse the startup banner
    for line in output.splitlines():
        line = line.strip()

        # Match session id
        match = SESSION_ID_PATTERN.match(line)
        if match:
            session_id = match.group(1)
            continue

        # Extract model if present
        if line.startswith("model:"):
            model = line.split(":", 1)[1].strip()
            continue

        # Extract workdir if present
        if line.startswith("workdir:"):
            workdir = line.split(":", 1)[1].strip()
            continue

    if not session_id:
        # Log the output for debugging
        logger.error(f"Failed to parse Codex output:\n{output}")
        if stderr:
            logger.error(f"Codex stderr:\n{stderr.decode()}")
        raise ValueError("No session id found in Codex output")

    logger.debug(f"Captured Codex session_id: {session_id}, model: {model}, workdir: {workdir}")

    return CodexSessionInfo(
        session_id=session_id,
        model=model,
        workdir=workdir,
    )
