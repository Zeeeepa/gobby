"""Unified transcript read layer with DB-first, gzip-archive fallback.

Tries the session_messages DB table first. If empty (messages were purged),
falls back to decompressing the gzip archive and parsing lines through the
appropriate TranscriptParser.
"""

from __future__ import annotations

import asyncio
import functools
import gzip
import logging
from typing import TYPE_CHECKING, Any

from gobby.sessions.transcript_archive import get_archive_dir

if TYPE_CHECKING:
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)

# LRU-cached decompression to avoid repeated gzip reads within a session
_ARCHIVE_CACHE_SIZE = 32


@functools.lru_cache(maxsize=_ARCHIVE_CACHE_SIZE)
def _decompress_archive(archive_path: str) -> list[str]:
    """Decompress a gzip archive and return lines.

    Cached so repeated reads of the same archive don't re-decompress.
    """
    with gzip.open(archive_path, "rt", encoding="utf-8") as f:
        return f.readlines()


def _parse_lines_to_dicts(
    lines: list[str],
    source: str,
) -> list[dict[str, Any]]:
    """Parse JSONL lines through the appropriate transcript parser.

    Returns dicts matching the session_messages column shape so callers
    get a consistent format regardless of source.
    """
    from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
    from gobby.sessions.transcripts.codex import CodexTranscriptParser
    from gobby.sessions.transcripts.gemini import GeminiTranscriptParser

    if source == "gemini":
        parser: Any = GeminiTranscriptParser()
    elif source == "codex":
        parser = CodexTranscriptParser()
    else:
        parser = ClaudeTranscriptParser()

    parsed = parser.parse_lines(lines, start_index=0)

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
                "raw_json": msg.raw_json,
            }
        )
    return results


class TranscriptReader:
    """Unified read layer: DB first, gzip archive fallback.

    Usage::

        reader = TranscriptReader(message_manager, session_manager)
        messages = await reader.get_messages(session_id, limit=50)
    """

    def __init__(
        self,
        message_manager: LocalSessionMessageManager,
        session_manager: LocalSessionManager,
        archive_dir: str | None = None,
    ):
        self._message_manager = message_manager
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
        # 1. Try DB
        messages = await self._message_manager.get_messages(
            session_id=session_id,
            limit=limit,
            offset=offset,
            role=role,
        )
        if messages:
            return messages

        # 2. DB empty — try gzip archive fallback
        return await self._read_from_archive(session_id, limit, offset, role)

    async def count_messages(self, session_id: str) -> int:
        """Count messages for a session, falling back to gzip archive."""
        db_count = await self._message_manager.count_messages(session_id)
        if db_count > 0:
            return db_count

        # Fallback: count from archive
        all_msgs = await self._read_from_archive(session_id, limit=999_999, offset=0)
        return len(all_msgs)

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
            all_messages = _parse_lines_to_dicts(lines, source)
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


def clear_archive_cache() -> None:
    """Clear the LRU cache for decompressed archives.

    Useful after writing new archives to ensure fresh reads.
    """
    _decompress_archive.cache_clear()
