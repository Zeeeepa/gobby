"""Tests for TranscriptReader — unified DB + gzip fallback read layer."""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.sessions.transcript_reader import TranscriptReader, clear_archive_cache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear LRU cache before each test."""
    clear_archive_cache()
    yield
    clear_archive_cache()


def _make_msg_dict(index: int, role: str = "assistant", content: str = "hi") -> dict:
    return {
        "session_id": "sess-1",
        "message_index": index,
        "role": role,
        "content": content,
        "content_type": "text",
        "tool_name": None,
        "tool_input": None,
        "tool_result": None,
        "tool_use_id": None,
        "timestamp": datetime.now(UTC).isoformat(),
        "raw_json": {},
    }


def _write_gzip_archive(archive_dir: Path, external_id: str, lines: list[dict]) -> Path:
    """Write JSONL lines to a gzip archive."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{external_id}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


class TestTranscriptReaderDBFirst:
    """TranscriptReader returns DB results when available."""

    @pytest.mark.asyncio
    async def test_returns_db_messages(self):
        message_manager = AsyncMock()
        session_manager = MagicMock()
        db_msgs = [_make_msg_dict(0), _make_msg_dict(1)]
        message_manager.get_messages.return_value = db_msgs
        message_manager.count_messages.return_value = 2

        reader = TranscriptReader(message_manager, session_manager)
        result = await reader.get_messages("sess-1", limit=50)

        assert result == db_msgs
        message_manager.get_messages.assert_called_once_with(
            session_id="sess-1", limit=50, offset=0, role=None
        )

    @pytest.mark.asyncio
    async def test_count_from_db(self):
        message_manager = AsyncMock()
        session_manager = MagicMock()
        message_manager.count_messages.return_value = 42

        reader = TranscriptReader(message_manager, session_manager)
        count = await reader.count_messages("sess-1")

        assert count == 42

    @pytest.mark.asyncio
    async def test_no_archive_fallback_when_db_has_data(self):
        message_manager = AsyncMock()
        session_manager = MagicMock()
        message_manager.get_messages.return_value = [_make_msg_dict(0)]

        reader = TranscriptReader(message_manager, session_manager)
        await reader.get_messages("sess-1")

        # session_manager.get should NOT be called (no fallback needed)
        session_manager.get.assert_not_called()


class TestTranscriptReaderGzipFallback:
    """TranscriptReader falls back to gzip archive when DB is empty."""

    @pytest.mark.asyncio
    async def test_falls_back_to_gzip(self, tmp_path: Path):
        archive_dir = tmp_path / "archives"
        external_id = "ext-abc123"

        # Write a gzip archive with Claude-format JSONL
        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_gzip_archive(archive_dir, external_id, lines)

        # Mock DB returning empty
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []
        message_manager.count_messages.return_value = 0

        session = MagicMock()
        session.external_id = external_id
        session.source = "claude"

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        result = await reader.get_messages("sess-1", limit=50)

        assert len(result) > 0
        # session_id should be filled in
        for msg in result:
            assert msg["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_count_falls_back_to_gzip(self, tmp_path: Path):
        archive_dir = tmp_path / "archives"
        external_id = "ext-count"

        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_gzip_archive(archive_dir, external_id, lines)

        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []
        message_manager.count_messages.return_value = 0

        session = MagicMock()
        session.external_id = external_id
        session.source = "claude"

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        count = await reader.count_messages("sess-1")

        assert count > 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_archive(self, tmp_path: Path):
        archive_dir = tmp_path / "empty-archives"
        archive_dir.mkdir()

        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []
        message_manager.count_messages.return_value = 0

        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        result = await reader.get_messages("sess-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_external_id(self):
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []

        session = MagicMock()
        session.external_id = None

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager)
        result = await reader.get_messages("sess-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_session_not_found(self):
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []

        session_manager = MagicMock()
        session_manager.get.return_value = None

        reader = TranscriptReader(message_manager, session_manager)
        result = await reader.get_messages("sess-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_role_filter_applied(self, tmp_path: Path):
        archive_dir = tmp_path / "archives"
        external_id = "ext-filter"

        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_gzip_archive(archive_dir, external_id, lines)

        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []

        session = MagicMock()
        session.external_id = external_id
        session.source = "claude"

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        result = await reader.get_messages("sess-1", role="user")

        for msg in result:
            assert msg["role"] == "user"

    @pytest.mark.asyncio
    async def test_pagination_applied(self, tmp_path: Path):
        archive_dir = tmp_path / "archives"
        external_id = "ext-page"

        # Write multiple lines
        lines = [
            {"type": "user", "message": {"role": "user", "content": f"msg {i}"}} for i in range(10)
        ]
        _write_gzip_archive(archive_dir, external_id, lines)

        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []

        session = MagicMock()
        session.external_id = external_id
        session.source = "claude"

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        result = await reader.get_messages("sess-1", limit=3, offset=2)

        assert len(result) <= 3
