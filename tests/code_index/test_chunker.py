"""Tests for code_index.chunker."""

from __future__ import annotations

import pytest

from gobby.code_index.chunker import chunk_file_content

pytestmark = pytest.mark.unit


def test_chunk_small_file() -> None:
    """A file smaller than chunk_size produces one chunk."""
    source = b"line1\nline2\nline3\n"
    chunks = chunk_file_content(source, "small.py", "proj-1", "python")
    assert len(chunks) == 1
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 3
    assert chunks[0].project_id == "proj-1"
    assert chunks[0].file_path == "small.py"
    assert chunks[0].language == "python"
    assert "line1" in chunks[0].content


def test_chunk_empty_file() -> None:
    """Empty file produces no chunks."""
    chunks = chunk_file_content(b"", "empty.py", "proj-1")
    assert chunks == []


def test_chunk_whitespace_only() -> None:
    """Whitespace-only file produces no chunks."""
    chunks = chunk_file_content(b"   \n  \n\n", "blank.py", "proj-1")
    assert chunks == []


def test_chunk_large_file_splits() -> None:
    """A file larger than chunk_size splits into multiple chunks."""
    lines = [f"line {i}\n" for i in range(250)]
    source = "".join(lines).encode()
    chunks = chunk_file_content(source, "big.py", "proj-1", chunk_size=100, overlap=10)

    assert len(chunks) >= 3
    # First chunk starts at line 1
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 100
    # Second chunk starts with overlap
    assert chunks[1].line_start == 91
    assert chunks[1].line_end == 190
    # Chunks have sequential indices
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunk_overlap_content() -> None:
    """Overlapping chunks share content at boundaries."""
    lines = [f"unique_marker_{i}\n" for i in range(120)]
    source = "".join(lines).encode()
    chunks = chunk_file_content(source, "overlap.py", "proj-1", chunk_size=100, overlap=10)

    assert len(chunks) == 2
    # Line 95 should appear in both chunks
    assert "unique_marker_94" in chunks[0].content
    assert "unique_marker_94" in chunks[1].content


def test_chunk_ids_are_deterministic() -> None:
    """Same input produces same chunk IDs."""
    source = b"hello\nworld\n"
    chunks1 = chunk_file_content(source, "f.py", "proj-1")
    chunks2 = chunk_file_content(source, "f.py", "proj-1")
    assert chunks1[0].id == chunks2[0].id


def test_chunk_ids_differ_across_files() -> None:
    """Different file paths produce different chunk IDs."""
    source = b"same content\n"
    c1 = chunk_file_content(source, "a.py", "proj-1")
    c2 = chunk_file_content(source, "b.py", "proj-1")
    assert c1[0].id != c2[0].id


def test_chunk_language_is_optional() -> None:
    """Language can be None."""
    source = b"some text\n"
    chunks = chunk_file_content(source, "file.txt", "proj-1", language=None)
    assert len(chunks) == 1
    assert chunks[0].language is None
