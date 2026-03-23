"""Tests for CodeIndexTrigger debounced post-edit indexing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from gobby.code_index.trigger import CodeIndexTrigger

pytestmark = pytest.mark.unit


@dataclass
class MockIndexResult:
    """Minimal mock for IndexResult."""

    files_indexed: int = 1
    symbols_found: int = 5
    duration_ms: int = 50
    project_id: str = "test-proj"


@pytest.fixture
def mock_indexer() -> AsyncMock:
    indexer = AsyncMock()
    indexer.index_changed_files = AsyncMock(return_value=MockIndexResult())
    return indexer


@pytest.fixture
async def trigger(mock_indexer: AsyncMock) -> CodeIndexTrigger:
    loop = asyncio.get_running_loop()
    return CodeIndexTrigger(
        indexer=mock_indexer,
        loop=loop,
        debounce_seconds=0.05,  # Fast debounce for tests
    )


# ── Basic flush ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_file_triggers_index(trigger: CodeIndexTrigger, mock_indexer: AsyncMock) -> None:
    """A single file notification triggers index_changed_files after debounce."""
    trigger._schedule_file("/src/foo.py", "proj-1", "/repo")

    # Wait for debounce to fire
    await asyncio.sleep(0.1)

    mock_indexer.index_changed_files.assert_called_once_with(
        project_id="proj-1",
        root_path="/repo",
        file_paths=["/src/foo.py"],
    )


# ── Debounce coalescing ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_files_batched(trigger: CodeIndexTrigger, mock_indexer: AsyncMock) -> None:
    """Multiple files in the same project are batched into one call."""
    trigger._schedule_file("/src/a.py", "proj-1", "/repo")
    trigger._schedule_file("/src/b.py", "proj-1", "/repo")
    trigger._schedule_file("/src/c.py", "proj-1", "/repo")

    await asyncio.sleep(0.1)

    mock_indexer.index_changed_files.assert_called_once()
    call_args = mock_indexer.index_changed_files.call_args
    assert call_args.kwargs["project_id"] == "proj-1"
    assert set(call_args.kwargs["file_paths"]) == {"/src/a.py", "/src/b.py", "/src/c.py"}


@pytest.mark.asyncio
async def test_same_file_deduped(trigger: CodeIndexTrigger, mock_indexer: AsyncMock) -> None:
    """Editing the same file multiple times results in one file in the batch."""
    trigger._schedule_file("/src/foo.py", "proj-1", "/repo")
    trigger._schedule_file("/src/foo.py", "proj-1", "/repo")
    trigger._schedule_file("/src/foo.py", "proj-1", "/repo")

    await asyncio.sleep(0.1)

    mock_indexer.index_changed_files.assert_called_once()
    call_args = mock_indexer.index_changed_files.call_args
    assert call_args.kwargs["file_paths"] == ["/src/foo.py"]


# ── Timer reset ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_debounce_timer_resets(trigger: CodeIndexTrigger, mock_indexer: AsyncMock) -> None:
    """New edits reset the debounce timer, delaying the flush."""
    trigger._schedule_file("/src/a.py", "proj-1", "/repo")

    # Wait less than debounce time, then add another file
    await asyncio.sleep(0.03)
    mock_indexer.index_changed_files.assert_not_called()

    trigger._schedule_file("/src/b.py", "proj-1", "/repo")

    # Wait for debounce after second edit
    await asyncio.sleep(0.1)

    # Should have been called once with both files
    mock_indexer.index_changed_files.assert_called_once()
    call_args = mock_indexer.index_changed_files.call_args
    assert set(call_args.kwargs["file_paths"]) == {"/src/a.py", "/src/b.py"}


# ── Multi-project isolation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_different_projects_independent(trigger: CodeIndexTrigger, mock_indexer: AsyncMock) -> None:
    """Different projects flush independently."""
    trigger._schedule_file("/repo1/a.py", "proj-1", "/repo1")
    trigger._schedule_file("/repo2/b.py", "proj-2", "/repo2")

    await asyncio.sleep(0.1)

    assert mock_indexer.index_changed_files.call_count == 2


# ── Error isolation ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_failure_does_not_propagate(trigger: CodeIndexTrigger, mock_indexer: AsyncMock) -> None:
    """Indexing failure is logged but doesn't raise."""
    mock_indexer.index_changed_files = AsyncMock(side_effect=RuntimeError("boom"))

    trigger._schedule_file("/src/foo.py", "proj-1", "/repo")

    # Should not raise
    await asyncio.sleep(0.1)

    mock_indexer.index_changed_files.assert_called_once()


# ── Empty flush ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_flush_is_noop(trigger: CodeIndexTrigger, mock_indexer: AsyncMock) -> None:
    """Flushing with no pending files does nothing."""
    await trigger._flush("nonexistent-project")
    mock_indexer.index_changed_files.assert_not_called()
