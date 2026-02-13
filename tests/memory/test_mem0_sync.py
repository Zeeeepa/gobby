"""Tests for Mem0SyncProcessor background sync."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.memory.mem0_client import Mem0ConnectionError
from gobby.memory.mem0_sync import Mem0SyncProcessor
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


def _setup(tmp_path, **config_overrides) -> tuple[MemoryManager, LocalDatabase]:
    """Create a MemoryManager with a fresh database."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(db_path)
    run_migrations(db)

    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, ?, datetime('now'), datetime('now'))",
        ("test-project", "Test Project"),
    )

    config = MemoryConfig(search_backend="tfidf", **config_overrides)
    manager = MemoryManager(db=db, config=config)
    return manager, db


def _mock_mem0_client() -> MagicMock:
    """Create a mock Mem0Client with default successful responses."""
    client = MagicMock()
    client.create = AsyncMock(
        return_value={"results": [{"id": "mem0-abc-123", "memory": "test content"}]}
    )
    client.search = AsyncMock(return_value={"results": []})
    client.delete = AsyncMock(return_value=True)
    client.close = AsyncMock()
    return client


# =============================================================================
# Mem0SyncProcessor: lifecycle
# =============================================================================


class TestMem0SyncProcessorLifecycle:
    """Test start/stop behavior."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self, tmp_path) -> None:
        """start() should create a background asyncio task."""
        manager, _ = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        proc = Mem0SyncProcessor(manager, sync_interval=0.1, max_backoff=1.0)
        await proc.start()
        try:
            assert proc._running is True
            assert proc._sync_task is not None
            assert not proc._sync_task.done()
        finally:
            await proc.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, tmp_path) -> None:
        """stop() should cancel the sync task and set _running to False."""
        manager, _ = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        proc = Mem0SyncProcessor(manager, sync_interval=0.1, max_backoff=1.0)
        await proc.start()
        await proc.stop()

        assert proc._running is False
        assert proc._sync_task is None

    @pytest.mark.asyncio
    async def test_start_noop_without_mem0_client(self, tmp_path) -> None:
        """start() should be a no-op when no Mem0 client is configured."""
        manager, _ = _setup(tmp_path)
        assert manager._mem0_client is None

        proc = Mem0SyncProcessor(manager, sync_interval=0.1)
        await proc.start()

        assert proc._running is False
        assert proc._sync_task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self, tmp_path) -> None:
        """Calling start() twice should not create a second task."""
        manager, _ = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        manager._mem0_client = _mock_mem0_client()

        proc = Mem0SyncProcessor(manager, sync_interval=0.1, max_backoff=1.0)
        await proc.start()
        first_task = proc._sync_task
        await proc.start()
        assert proc._sync_task is first_task
        await proc.stop()


# =============================================================================
# Mem0SyncProcessor: sync loop
# =============================================================================


class TestMem0SyncProcessorSync:
    """Test the background sync loop behavior."""

    @pytest.mark.asyncio
    async def test_sync_loop_pushes_unsynced_memories(self, tmp_path) -> None:
        """The sync loop should push memories with mem0_id IS NULL."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        # Create a memory (remember() no longer calls Mem0 directly)
        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(content="Test memory", project_id="test-project")

        # Verify it's unsynced
        row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
        assert row["mem0_id"] is None

        # Run the processor and poll until sync completes (avoids flaky fixed sleep)
        proc = Mem0SyncProcessor(manager, sync_interval=0.05, max_backoff=1.0)
        await proc.start()

        # Poll until mem0_id is set or timeout
        timeout = 2.0
        elapsed = 0.0
        row = None
        while elapsed < timeout:
            row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
            if row and row["mem0_id"] is not None:
                break
            await asyncio.sleep(0.01)
            elapsed += 0.01

        await proc.stop()

        # Memory should now have mem0_id
        assert row is not None and row["mem0_id"] == "mem0-abc-123"

    @pytest.mark.asyncio
    async def test_sync_loop_backoff_on_connection_error(self, tmp_path) -> None:
        """The sync loop should back off when Mem0 is unreachable."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        # Create an unsynced memory
        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            await manager.remember(content="Test memory", project_id="test-project")

        # Make _lazy_sync raise Mem0ConnectionError
        manager._lazy_sync = AsyncMock(side_effect=Mem0ConnectionError("unreachable"))

        proc = Mem0SyncProcessor(manager, sync_interval=0.05, max_backoff=0.5)
        await proc.start()
        await asyncio.sleep(0.15)  # Let a couple cycles run
        await proc.stop()

        assert proc._backoff_active is True

    @pytest.mark.asyncio
    async def test_sync_loop_resets_backoff_on_success(self, tmp_path) -> None:
        """Backoff should reset after a successful sync."""
        manager, _ = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        # Mock _lazy_sync to succeed
        manager._lazy_sync = AsyncMock(return_value=0)

        proc = Mem0SyncProcessor(manager, sync_interval=0.05, max_backoff=1.0)
        proc._backoff_active = True  # pretend we were in backoff

        await proc.start()
        await asyncio.sleep(0.15)
        await proc.stop()

        assert proc._backoff_active is False


# =============================================================================
# Mem0SyncProcessor: observability stats
# =============================================================================


class TestMem0SyncProcessorStats:
    """Test the stats property for observability."""

    def test_stats_shows_pending_count(self, tmp_path) -> None:
        """stats should show count of memories with mem0_id IS NULL."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        manager._mem0_client = _mock_mem0_client()

        proc = Mem0SyncProcessor(manager, sync_interval=10.0)

        # No memories yet
        stats = proc.stats
        assert stats["pending"] == 0
        assert stats["last_sync_at"] is None
        assert stats["last_sync_count"] == 0
        assert stats["backoff_active"] is False

    def test_stats_counts_unsynced_memories(self, tmp_path) -> None:
        """stats should count memories with mem0_id IS NULL."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        manager._mem0_client = _mock_mem0_client()

        # Insert memories directly — one synced, one not
        db.execute(
            "INSERT INTO memories (id, content, memory_type, importance, project_id, "
            "created_at, updated_at, mem0_id) VALUES (?, ?, ?, ?, ?, datetime('now'), "
            "datetime('now'), ?)",
            ("mem-1", "synced", "fact", 0.5, "test-project", "mem0-xyz"),
        )
        db.execute(
            "INSERT INTO memories (id, content, memory_type, importance, project_id, "
            "created_at, updated_at, mem0_id) VALUES (?, ?, ?, ?, ?, datetime('now'), "
            "datetime('now'), ?)",
            ("mem-2", "unsynced", "fact", 0.5, "test-project", None),
        )

        proc = Mem0SyncProcessor(manager, sync_interval=10.0)
        stats = proc.stats
        assert stats["pending"] == 1


# =============================================================================
# Search merge: unsynced memories appear in results
# =============================================================================


class TestSearchMergeUnsynced:
    """Test that unsynced memories appear in Mem0 search results."""

    @pytest.mark.asyncio
    async def test_recall_includes_unsynced_in_mem0_results(self, tmp_path) -> None:
        """When Mem0 returns results, unsynced local memories should be merged in."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        # Create a memory (stays unsynced since remember() no longer calls Mem0)
        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

        # Mem0 search returns empty (memory not synced yet)
        mock_client.search = AsyncMock(return_value={"results": []})

        results = manager.recall(query="dark mode", project_id="test-project", min_importance=0.0)

        # The unsynced memory should appear via merge
        assert any(m.id == memory.id for m in results)


# =============================================================================
# get_stats(): mem0_sync section
# =============================================================================


class TestGetStatsMem0Sync:
    """Test mem0_sync section in get_stats()."""

    @pytest.mark.asyncio
    async def test_get_stats_includes_mem0_sync(self, tmp_path) -> None:
        """get_stats() should include mem0_sync when Mem0 is configured."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        manager._mem0_client = _mock_mem0_client()

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            await manager.remember(content="Test memory", project_id="test-project")

        stats = manager.get_stats(project_id="test-project")
        assert "mem0_sync" in stats
        assert stats["mem0_sync"]["pending"] == 1

    def test_get_stats_no_mem0_sync_in_standalone(self, tmp_path) -> None:
        """get_stats() should not include mem0_sync in standalone mode."""
        manager, _ = _setup(tmp_path)
        stats = manager.get_stats()
        assert "mem0_sync" not in stats
