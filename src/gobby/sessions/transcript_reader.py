"""Unified transcript read layer: live JSONL → gzip archive.

Reads from the live JSONL transcript file on disk (active/paused sessions).
If no JSONL exists (cleaned up after expiry), falls back to the gzip archive.
"""

from __future__ import annotations

import asyncio
import functools
import gzip
import logging
import os
import zlib
from typing import TYPE_CHECKING, Any

from gobby.sessions.transcript_archive import get_archive_dir

if TYPE_CHECKING:
    from gobby.sessions.transcript_renderer import RenderedMessage
    from gobby.sessions.transcripts.base import ParsedMessage
    from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
    from gobby.sessions.transcripts.codex import CodexTranscriptParser
    from gobby.sessions.transcripts.gemini import GeminiTranscriptParser
    from gobby.storage.sessions import LocalSessionManager

    TranscriptParser = ClaudeTranscriptParser | GeminiTranscriptParser | CodexTranscriptParser

from gobby.sessions.transcript_renderer import render_transcript

logger = logging.getLogger(__name__)

# LRU-cached decompression to avoid repeated gzip reads within a session
_ARCHIVE_CACHE_SIZE = 32


@functools.lru_cache(maxsize=_ARCHIVE_CACHE_SIZE)
def _decompress_archive(archive_path: str) -> list[str]:
    """Decompress a gzip archive and return lines.

    Cached so repeated reads of the same archive don't re-decompress.
    Handles truncated archives gracefully by returning what was read.
    """
    lines = []
    try:
        with gzip.open(archive_path, "rt", encoding="utf-8") as f:
            for line in f:
                lines.append(line)
    except (EOFError, gzip.BadGzipFile, zlib.error) as e:
        logger.warning("Truncated or malformed gzip archive %s: %s", archive_path, e)
    return lines


def _get_parser(source: str, session_id: str | None = None) -> TranscriptParser:
    """Get the appropriate transcript parser for a source."""
    from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
    from gobby.sessions.transcripts.codex import CodexTranscriptParser
    from gobby.sessions.transcripts.gemini import GeminiTranscriptParser

    if source == "gemini":
        return GeminiTranscriptParser(session_id=session_id)
    elif source == "codex":
        return CodexTranscriptParser(session_id=session_id)
    else:
        return ClaudeTranscriptParser(session_id=session_id)


def _parse_lines(
    lines: list[str], source: str, session_id: str | None = None
) -> list[ParsedMessage]:
    """Parse lines into ParsedMessage objects."""
    parser = _get_parser(source, session_id=session_id)
    return parser.parse_lines(lines, start_index=0)


def _parse_lines_to_dicts(
    lines: list[str],
    source: str,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Parse JSONL lines through the appropriate transcript parser.

    Returns dicts matching the session_messages column shape so callers
    get a consistent format regardless of source.
    """
    parsed = _parse_lines(lines, source, session_id=session_id)

    results: list[dict[str, Any]] = []
    for msg in parsed:
        results.append(
            {
                "session_id": None,  # not available from archive
                "message_index": msg.index,
                "role": msg.role,
                "content": msg.content,
                "content_type": msg.content_type,
                "tool_name": msg.tool_name,
                "tool_input": msg.tool_input,
                "tool_result": msg.tool_result,
                "tool_use_id": msg.tool_use_id,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "raw_json": msg.raw_json,  # kept for archive writes, not stored in DB
            }
        )
    return results


class TranscriptReader:
    """Unified read layer: live JSONL first, gzip archive fallback.

    Usage::

        reader = TranscriptReader(session_manager=session_manager)
        messages = await reader.get_messages(session_id, limit=50)
    """

    def __init__(
        self,
        session_manager: LocalSessionManager,
        archive_dir: str | None = None,
        # Deprecated: kept for backwards-compat callers, ignored
        message_manager: object | None = None,
    ):
        if message_manager is not None:
            import warnings

            warnings.warn(
                "message_manager is deprecated and ignored",
                DeprecationWarning,
                stacklevel=2,
            )
        self._session_manager = session_manager
        self._archive_dir = archive_dir

    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get messages for a session, falling back to gzip archive.

        Args:
            session_id: Session UUID
            limit: Maximum messages to return
            offset: Pagination offset
            role: Optional role filter

        Returns:
            List of message dicts
        """
        # 1. Try live JSONL file (active/paused sessions)
        jsonl_messages = await self._read_from_jsonl(session_id, limit, offset, role)
        if jsonl_messages:
            return jsonl_messages

        # 2. JSONL gone — try gzip archive (expired sessions)
        return await self._read_from_archive(session_id, limit, offset, role)

    async def get_rendered_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RenderedMessage]:
        """Get grouped, rendered messages for a session.

        Skips the database entirely (avoids corrupted str() data) and reads
        directly from JSONL or gzip archive.

        Args:
            session_id: Session UUID
            limit: Maximum turns to return
            offset: Pagination offset

        Returns:
            List of RenderedMessage objects
        """
        # 1. Try live JSONL file
        parsed_messages = await self._get_parsed_messages_from_jsonl(session_id)

        # 2. Fallback to gzip archive
        if not parsed_messages:
            parsed_messages = await self._get_parsed_messages_from_archive(session_id)

        if not parsed_messages:
            return []

        # 3. Render transcript (group blocks into turns)
        rendered = render_transcript(parsed_messages, session_id=session_id)

        # 4. Apply pagination
        return rendered[offset : offset + limit]

    async def count_messages(self, session_id: str) -> int:
        """Count messages for a session from live JSONL or gzip archive."""
        session = self._session_manager.get(session_id)
        if not session:
            return 0

        # Fallback 1: count lines from live JSONL file
        jsonl_path = getattr(session, "jsonl_path", None)
        if jsonl_path and os.path.isfile(jsonl_path):
            try:
                lines = await asyncio.to_thread(self._read_jsonl_lines, jsonl_path)
                return sum(1 for line in lines if line.strip())
            except Exception as e:
                logger.warning(
                    "Failed to count messages from JSONL for session %s: %s",
                    session_id,
                    e,
                )

        # Fallback 2: count lines from gzip archive
        if session.external_id:
            archive_dir = get_archive_dir(self._archive_dir)
            archive_path = archive_dir / f"{session.external_id}.jsonl.gz"
            if archive_path.is_file():
                lines = await asyncio.to_thread(_decompress_archive, str(archive_path))
                return sum(1 for line in lines if line.strip())

        return 0

    async def _get_parsed_messages_from_archive(self, session_id: str) -> list[ParsedMessage]:
        """Read and parse ParsedMessages from gzip archive."""
        session = self._session_manager.get(session_id)
        if not session or not session.external_id:
            return []

        archive_dir = get_archive_dir(self._archive_dir)
        archive_path = archive_dir / f"{session.external_id}.jsonl.gz"

        if not archive_path.is_file():
            return []

        source = session.source or "claude"

        try:
            lines = await asyncio.to_thread(_decompress_archive, str(archive_path))
            return _parse_lines(lines, source, session_id=session_id)
        except Exception as e:
            logger.warning("Failed to read archive for session %s: %s", session_id, e)
            return []

    async def _get_parsed_messages_from_jsonl(self, session_id: str) -> list[ParsedMessage]:
        """Read and parse ParsedMessages from live JSONL file."""
        session = self._session_manager.get(session_id)
        if not session:
            return []

        jsonl_path = getattr(session, "jsonl_path", None)
        if not jsonl_path or not os.path.isfile(jsonl_path):
            return []

        source = session.source or "claude"

        try:
            lines = await asyncio.to_thread(self._read_jsonl_lines, jsonl_path)
            return _parse_lines(lines, source, session_id=session_id)
        except Exception as e:
            logger.warning("Failed to read JSONL for session %s: %s", session_id, e)
            return []

    async def _read_from_archive(
        self,
        session_id: str,
        limit: int,
        offset: int,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read messages from gzip archive for a session."""
        session = self._session_manager.get(session_id)
        if not session or not session.external_id:
            return []

        archive_dir = get_archive_dir(self._archive_dir)
        archive_path = archive_dir / f"{session.external_id}.jsonl.gz"

        if not archive_path.is_file():
            return []

        source = session.source or "claude"

        try:
            lines = await asyncio.to_thread(_decompress_archive, str(archive_path))
            all_messages = _parse_lines_to_dicts(lines, source, session_id=session_id)
        except Exception as e:
            logger.warning("Failed to read archive for session %s: %s", session_id, e)
            return []

        # Fill in session_id
        for msg in all_messages:
            msg["session_id"] = session_id

        # Apply role filter
        if role:
            all_messages = [m for m in all_messages if m["role"] == role]

        # Apply pagination
        return all_messages[offset : offset + limit]

    async def _read_from_jsonl(
        self,
        session_id: str,
        limit: int,
        offset: int,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read messages from a live JSONL transcript file on disk."""
        session = self._session_manager.get(session_id)
        if not session:
            return []

        jsonl_path = getattr(session, "jsonl_path", None)
        if not jsonl_path or not os.path.isfile(jsonl_path):
            return []

        source = session.source or "claude"

        try:
            lines = await asyncio.to_thread(self._read_jsonl_lines, jsonl_path)
            all_messages = _parse_lines_to_dicts(lines, source, session_id=session_id)
        except Exception as e:
            logger.warning("Failed to read JSONL for session %s: %s", session_id, e)
            return []

        # Fill in session_id
        for msg in all_messages:
            msg["session_id"] = session_id

        # Apply role filter
        if role:
            all_messages = [m for m in all_messages if m["role"] == role]

        # Apply pagination
        return all_messages[offset : offset + limit]

    @staticmethod
    def _read_jsonl_lines(path: str) -> list[str]:
        """Read lines from a JSONL file. Runs in a thread."""
        with open(path, encoding="utf-8") as f:
            return f.readlines()


def clear_archive_cache() -> None:
    """Clear the LRU cache for decompressed archives.

    Useful after writing new archives to ensure fresh reads.
    """
    _decompress_archive.cache_clear()
