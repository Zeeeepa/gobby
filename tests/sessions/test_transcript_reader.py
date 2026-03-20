"""Tests for TranscriptReader — unified DB + gzip fallback read layer."""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.sessions.transcript_reader import TranscriptReader, clear_archive_cache
from gobby.sessions.transcript_renderer import RenderedMessage


# Helper to write a plain JSONL file (not gzipped)
def _write_jsonl_file(path: Path, lines: list[dict]) -> Path:
    """Write JSONL lines to a plain file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


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
        session.jsonl_path = None  # no live JSONL — forces gzip fallback

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

        assert len(result) == 3


class TestTranscriptReaderJsonlFallback:
    """TranscriptReader falls back to live JSONL when DB and archive are empty."""

    @pytest.mark.asyncio
    async def test_falls_back_to_jsonl(self, tmp_path: Path):
        jsonl_path = tmp_path / "transcript.jsonl"
        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_jsonl_file(jsonl_path, lines)

        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []
        message_manager.count_messages.return_value = 0

        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"
        session.jsonl_path = str(jsonl_path)

        session_manager = MagicMock()
        session_manager.get.return_value = session

        # No archive dir — forces archive fallback to return []
        archive_dir = tmp_path / "empty-archives"
        archive_dir.mkdir()

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        result = await reader.get_messages("sess-1", limit=50)

        assert len(result) > 0
        for msg in result:
            assert msg["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_count_falls_back_to_jsonl(self, tmp_path: Path):
        jsonl_path = tmp_path / "transcript.jsonl"
        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_jsonl_file(jsonl_path, lines)

        message_manager = AsyncMock()
        message_manager.count_messages.return_value = 0

        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"
        session.jsonl_path = str(jsonl_path)

        session_manager = MagicMock()
        session_manager.get.return_value = session

        archive_dir = tmp_path / "empty-archives"
        archive_dir.mkdir()

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        count = await reader.count_messages("sess-1")

        assert count > 0

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_jsonl(self, tmp_path: Path):
        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []
        message_manager.count_messages.return_value = 0

        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"
        session.jsonl_path = "/nonexistent/path.jsonl"

        session_manager = MagicMock()
        session_manager.get.return_value = session

        archive_dir = tmp_path / "empty-archives"
        archive_dir.mkdir()

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        result = await reader.get_messages("sess-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_role_filter_applied(self, tmp_path: Path):
        jsonl_path = tmp_path / "transcript.jsonl"
        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_jsonl_file(jsonl_path, lines)

        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []

        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"
        session.jsonl_path = str(jsonl_path)

        session_manager = MagicMock()
        session_manager.get.return_value = session

        archive_dir = tmp_path / "empty-archives"
        archive_dir.mkdir()

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))
        result = await reader.get_messages("sess-1", role="user")

        for msg in result:
            assert msg["role"] == "user"

    @pytest.mark.asyncio
    async def test_pagination_applied(self, tmp_path: Path):
        jsonl_path = tmp_path / "transcript.jsonl"
        lines = [
            {"type": "user", "message": {"role": "user", "content": f"msg {i}"}} for i in range(10)
        ]
        _write_jsonl_file(jsonl_path, lines)

        message_manager = AsyncMock()
        message_manager.get_messages.return_value = []

        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"
        session.jsonl_path = str(jsonl_path)

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(tmp_path))
        result = await reader.get_messages("sess-1", limit=3, offset=2)

        assert len(result) == 3


class TestTranscriptReaderRendered:
    """Tests for the new get_rendered_messages method."""

    @pytest.mark.asyncio
    async def test_get_rendered_messages_jsonl(self, tmp_path: Path):
        jsonl_path = tmp_path / "transcript.jsonl"
        # Claude format
        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_jsonl_file(jsonl_path, lines)

        message_manager = AsyncMock()
        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"
        session.jsonl_path = str(jsonl_path)

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager)

        result = await reader.get_rendered_messages("sess-1")

        assert len(result) == 2
        assert isinstance(result[0], RenderedMessage)
        assert result[0].role == "user"
        assert result[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_get_rendered_messages_gzip(self, tmp_path: Path):
        archive_dir = tmp_path / "archives"
        external_id = "ext-123"
        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            },
        ]
        _write_gzip_archive(archive_dir, external_id, lines)

        message_manager = AsyncMock()
        session = MagicMock()
        session.external_id = external_id
        session.source = "claude"
        session.jsonl_path = None

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))

        result = await reader.get_rendered_messages("sess-1")

        assert len(result) == 2
        assert isinstance(result[0], RenderedMessage)

    @pytest.mark.asyncio
    async def test_get_rendered_messages_pagination(self, tmp_path: Path):
        jsonl_path = tmp_path / "transcript.jsonl"
        lines = []
        for i in range(10):
            lines.append({"type": "user", "message": {"role": "user", "content": f"msg {i}"}})
        _write_jsonl_file(jsonl_path, lines)

        message_manager = AsyncMock()
        session = MagicMock()
        session.external_id = "no-archive"
        session.source = "claude"
        session.jsonl_path = str(jsonl_path)

        session_manager = MagicMock()
        session_manager.get.return_value = session

        reader = TranscriptReader(message_manager, session_manager)

        result = await reader.get_rendered_messages("sess-1", limit=3, offset=2)

        assert len(result) == 3
        assert "msg 2" in result[0].content
        assert "msg 4" in result[2].content

    @pytest.mark.asyncio
    async def test_get_rendered_messages_truncated_gzip(self, tmp_path: Path):
        archive_dir = tmp_path / "archives"
        external_id = "ext-truncated"
        archive_dir.mkdir(parents=True, exist_ok=True)
        path = archive_dir / f"{external_id}.jsonl.gz"

        # Write valid gzip data first
        valid_line = (
            json.dumps({"type": "user", "message": {"role": "user", "content": "valid"}}) + "\n"
        )
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(valid_line)

        # Append some garbage to truncate it / make it invalid
        with open(path, "ab") as f:
            f.write(b"\x00\x01\x02\x03" * 10)

        message_manager = AsyncMock()
        session = MagicMock()
        session.external_id = external_id
        session.source = "claude"
        session.jsonl_path = None

        session_manager = MagicMock()
        session_manager.get.return_value = session

        clear_archive_cache()
        reader = TranscriptReader(message_manager, session_manager, archive_dir=str(archive_dir))

        # Should not raise exception, should return what it could read
        result = await reader.get_rendered_messages("sess-1")
        assert len(result) >= 1
        assert "valid" in result[0].content

    @pytest.mark.asyncio
    async def test_get_rendered_messages_empty_session(self):
        message_manager = AsyncMock()
        session_manager = MagicMock()
        session_manager.get.return_value = None

        reader = TranscriptReader(message_manager, session_manager)
        result = await reader.get_rendered_messages("empty-session")
        assert result == []
