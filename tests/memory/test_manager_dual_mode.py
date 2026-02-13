"""Tests for MemoryManager dual-mode (SQLite + Mem0) operation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.memory.mem0_client import Mem0ConnectionError
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


def _setup(tmp_path, **config_overrides) -> tuple[MemoryManager, LocalDatabase]:
    """Create a MemoryManager with a fresh database."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(db_path)
    run_migrations(db)

    # Create project
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
    client.search = AsyncMock(
        return_value={"results": [{"id": "mem0-abc-123", "memory": "test content", "score": 0.95}]}
    )
    client.delete = AsyncMock(return_value=True)
    client.update = AsyncMock(return_value={"id": "mem0-abc-123", "memory": "updated content"})
    client.close = AsyncMock()
    return client


# =============================================================================
# Initialization: Mem0Client creation
# =============================================================================


class TestDualModeInit:
    """Test that Mem0Client is created only when mem0_url is configured."""

    def test_standalone_mode_no_mem0_client(self, tmp_path) -> None:
        """When mem0_url is not set, _mem0_client should be None."""
        manager, _ = _setup(tmp_path)
        assert manager._mem0_client is None

    def test_dual_mode_creates_mem0_client(self, tmp_path) -> None:
        """When mem0_url is set, _mem0_client should be initialized."""
        manager, _ = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        assert manager._mem0_client is not None

    def test_dual_mode_passes_config_to_client(self, tmp_path) -> None:
        """Mem0Client should receive url and api_key from config."""
        with patch("gobby.memory.manager.Mem0Client") as MockClient:
            manager, _ = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
            MockClient.assert_called_once_with(
                base_url="http://localhost:8888",
                api_key="test-key",
                timeout=90.0,
            )


# =============================================================================
# remember(): dual-mode storage
# =============================================================================


class TestRememberDualMode:
    """Test remember() stores in SQLite then indexes in Mem0."""

    @pytest.mark.asyncio
    async def test_remember_stores_locally_without_blocking_mem0(self, tmp_path) -> None:
        """remember() should store locally without blocking on Mem0 (async queue)."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

        # Memory should be stored in SQLite
        assert memory.id is not None
        local = manager.get_memory(memory.id)
        assert local is not None

        # Mem0 create should NOT have been called (deferred to background sync)
        mock_client.create.assert_not_called()

        # mem0_id should be NULL (pending sync)
        row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
        assert row["mem0_id"] is None

    @pytest.mark.asyncio
    async def test_remember_then_lazy_sync_stores_mem0_id(self, tmp_path) -> None:
        """remember() leaves mem0_id NULL; _lazy_sync() populates it."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

        # mem0_id should be NULL immediately after remember()
        row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
        assert row is not None
        assert row["mem0_id"] is None

        # Now run lazy sync — should populate mem0_id
        synced = await manager._lazy_sync()
        assert synced == 1

        row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
        assert row is not None
        assert row["mem0_id"] == "mem0-abc-123"

    @pytest.mark.asyncio
    async def test_remember_mem0_unreachable_stores_locally(self, tmp_path) -> None:
        """When Mem0 is unreachable, remember() should still store in SQLite."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        mock_client.create = AsyncMock(side_effect=Mem0ConnectionError("Connection refused"))
        manager._mem0_client = mock_client

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

        # Memory should still be in SQLite
        assert memory.id is not None
        local = manager.get_memory(memory.id)
        assert local is not None

        # mem0_id should be NULL (not synced)
        row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
        assert row is not None
        assert row["mem0_id"] is None

    @pytest.mark.asyncio
    async def test_remember_standalone_skips_mem0(self, tmp_path) -> None:
        """In standalone mode, remember() should not touch Mem0 at all."""
        manager, _ = _setup(tmp_path)
        assert manager._mem0_client is None

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="Standalone memory",
                project_id="test-project",
            )

        assert memory.id is not None


# =============================================================================
# recall(): dual-mode search
# =============================================================================


class TestRecallDualMode:
    """Test recall() queries Mem0 when configured, falls back to local."""

    @pytest.mark.asyncio
    async def test_recall_queries_mem0(self, tmp_path) -> None:
        """recall() should search Mem0 when configured and reachable."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        # Create a memory locally first (with mem0_id)
        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

        # Configure mock to return the memory from mem0
        mock_client.search = AsyncMock(
            return_value={
                "results": [
                    {
                        "id": "mem0-abc-123",
                        "memory": "User prefers dark mode",
                        "score": 0.95,
                        "metadata": {"gobby_id": memory.id},
                    }
                ]
            }
        )

        results = manager.recall(query="dark mode", project_id="test-project")

        # Mem0 search should have been called
        mock_client.search.assert_called_once()

        # Should return local memories enriched by mem0 results
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_recall_mem0_unreachable_falls_back(
        self, tmp_path, enable_log_propagation, caplog
    ) -> None:
        """When Mem0 is unreachable, recall() should fall back to local search."""
        manager, _ = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        mock_client.search = AsyncMock(side_effect=Mem0ConnectionError("Connection refused"))
        manager._mem0_client = mock_client

        # Create a memory locally
        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

        import logging

        with caplog.at_level(logging.WARNING, logger="gobby.memory.manager"):
            results = manager.recall(
                query="dark mode", project_id="test-project", min_importance=0.0
            )

        # Should fall back to local search and still return results
        assert len(results) >= 1

        # Should log a warning (once)
        assert any("Mem0" in record.message for record in caplog.records)


# =============================================================================
# forget(): dual-mode deletion
# =============================================================================


class TestForgetDualMode:
    """Test forget() deletes from both SQLite and Mem0."""

    @pytest.mark.asyncio
    async def test_forget_deletes_from_mem0(self, tmp_path) -> None:
        """forget() should delete from Mem0 when memory has mem0_id."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        manager._mem0_client = mock_client

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

        # Simulate background sync having already populated mem0_id
        db.execute(
            "UPDATE memories SET mem0_id = ? WHERE id = ?",
            ("mem0-abc-123", memory.id),
        )

        result = await manager.forget(memory.id)
        assert result is True

        # Mem0 delete should have been called with the mem0_id
        mock_client.delete.assert_called_once_with("mem0-abc-123")

    @pytest.mark.asyncio
    async def test_forget_without_mem0_id_skips_mem0(self, tmp_path) -> None:
        """forget() should skip Mem0 deletion when memory has no mem0_id."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        mock_client.create = AsyncMock(side_effect=Mem0ConnectionError("Connection refused"))
        manager._mem0_client = mock_client

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="Unsynced memory",
                project_id="test-project",
            )

        mock_client.delete.reset_mock()
        result = await manager.forget(memory.id)
        assert result is True

        # Mem0 delete should NOT have been called (no mem0_id)
        mock_client.delete.assert_not_called()


# =============================================================================
# _lazy_sync(): background sync of unsynced memories
# =============================================================================


class TestLazySync:
    """Test _lazy_sync() indexes unsynced memories in Mem0."""

    @pytest.mark.asyncio
    async def test_lazy_sync_indexes_unsynced(self, tmp_path) -> None:
        """_lazy_sync() should index memories with mem0_id IS NULL."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        # First call fails (connection refused), second succeeds
        mock_client.create = AsyncMock(side_effect=Mem0ConnectionError("Connection refused"))
        manager._mem0_client = mock_client

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            memory = await manager.remember(
                content="Unsynced memory",
                project_id="test-project",
            )

        # Verify mem0_id is NULL
        row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
        assert row["mem0_id"] is None

        # Now make mem0 reachable
        mock_client.create = AsyncMock(
            return_value={"results": [{"id": "mem0-synced-456", "memory": "Unsynced memory"}]}
        )

        synced = await manager._lazy_sync()
        assert synced == 1

        # Verify mem0_id is now set
        row = db.fetchone("SELECT mem0_id FROM memories WHERE id = ?", (memory.id,))
        assert row["mem0_id"] == "mem0-synced-456"

    @pytest.mark.asyncio
    async def test_lazy_sync_no_op_in_standalone(self, tmp_path) -> None:
        """_lazy_sync() should return 0 in standalone mode."""
        manager, _ = _setup(tmp_path)
        synced = await manager._lazy_sync()
        assert synced == 0

    @pytest.mark.asyncio
    async def test_lazy_sync_handles_partial_failure(self, tmp_path) -> None:
        """_lazy_sync() should continue even if some memories fail to sync."""
        manager, db = _setup(tmp_path, mem0_url="http://localhost:8888", mem0_api_key="test-key")
        mock_client = _mock_mem0_client()
        # All creates fail initially
        mock_client.create = AsyncMock(side_effect=Mem0ConnectionError("Connection refused"))
        manager._mem0_client = mock_client

        with patch("gobby.memory.services.embeddings.is_embedding_available", return_value=False):
            await manager.remember(content="Memory one", project_id="test-project")
            await manager.remember(content="Memory two", project_id="test-project")

        # On sync: first succeeds, second fails
        call_count = 0

        async def _selective_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"results": [{"id": "mem0-ok-1", "memory": "Memory one"}]}
            raise Mem0ConnectionError("Still failing")

        mock_client.create = AsyncMock(side_effect=_selective_create)

        synced = await manager._lazy_sync()
        assert synced == 1  # Only one succeeded
