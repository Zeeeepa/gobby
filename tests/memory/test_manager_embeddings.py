"""Tests for embedding generation hooked into memory CRUD lifecycle."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase
from gobby.storage.memory_embeddings import MemoryEmbeddingManager
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit

FAKE_EMBEDDING = [0.1, 0.2, 0.3, 0.4, 0.5]


def _setup(tmp_path, **config_overrides) -> tuple[MemoryManager, MemoryEmbeddingManager]:
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
    embedding_mgr = MemoryEmbeddingManager(db)
    return manager, embedding_mgr


# =============================================================================
# remember() generates embeddings
# =============================================================================


class TestRememberGeneratesEmbedding:
    """Test that remember() generates and stores embeddings for new memories."""

    @pytest.mark.asyncio
    async def test_remember_generates_embedding(self, tmp_path) -> None:
        """remember() should generate and store an embedding for the new memory."""
        manager, embedding_mgr = _setup(tmp_path)

        with patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            return_value=FAKE_EMBEDDING,
        ) as mock_gen, patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ):
            memory = await manager.remember(
                content="User prefers dark mode",
                project_id="test-project",
            )

            mock_gen.assert_called_once()

        # Embedding should be stored
        stored = embedding_mgr.get_embedding(memory.id)
        assert stored is not None
        assert stored.embedding == pytest.approx(FAKE_EMBEDDING, abs=1e-6)
        assert stored.memory_id == memory.id
        assert stored.project_id == "test-project"
        assert stored.embedding_model == "text-embedding-3-small"
        expected_hash = hashlib.sha256(b"User prefers dark mode").hexdigest()
        assert stored.text_hash == expected_hash

    @pytest.mark.asyncio
    async def test_remember_skips_embedding_when_unavailable(self, tmp_path) -> None:
        """remember() should skip embedding generation when embeddings are unavailable."""
        manager, embedding_mgr = _setup(tmp_path)

        with patch(
            "gobby.memory.manager.is_embedding_available", return_value=False
        ):
            memory = await manager.remember(
                content="Some fact",
                project_id="test-project",
            )

        # Memory created, but no embedding
        assert memory is not None
        stored = embedding_mgr.get_embedding(memory.id)
        assert stored is None

    @pytest.mark.asyncio
    async def test_remember_succeeds_when_embedding_fails(self, tmp_path) -> None:
        """remember() should succeed even if embedding generation fails (graceful degradation)."""
        manager, embedding_mgr = _setup(tmp_path)

        with patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ), patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API error"),
        ):
            memory = await manager.remember(
                content="Important fact",
                project_id="test-project",
            )

        # Memory should still be created
        assert memory is not None
        assert memory.content == "Important fact"
        # No embedding stored
        stored = embedding_mgr.get_embedding(memory.id)
        assert stored is None


# =============================================================================
# update_memory() regenerates embeddings when content changes
# =============================================================================


class TestUpdateRegeneratesEmbedding:
    """Test that updating memory content regenerates the embedding."""

    @pytest.mark.asyncio
    async def test_update_content_regenerates_embedding(self, tmp_path) -> None:
        """Updating content should regenerate the embedding with new text_hash."""
        manager, embedding_mgr = _setup(tmp_path)

        new_embedding = [0.9, 0.8, 0.7, 0.6, 0.5]

        with patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            return_value=FAKE_EMBEDDING,
        ), patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ):
            memory = await manager.remember(
                content="Original content",
                project_id="test-project",
            )

        original_hash = embedding_mgr.get_embedding(memory.id).text_hash

        # Now update content
        with patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            return_value=new_embedding,
        ), patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ):
            await manager.aupdate_memory(memory.id, content="Updated content")

        stored = embedding_mgr.get_embedding(memory.id)
        assert stored is not None
        assert stored.embedding == pytest.approx(new_embedding, abs=1e-6)
        new_hash = hashlib.sha256(b"Updated content").hexdigest()
        assert stored.text_hash == new_hash
        assert stored.text_hash != original_hash

    @pytest.mark.asyncio
    async def test_update_without_content_skips_embedding(self, tmp_path) -> None:
        """Updating only importance/tags should NOT regenerate the embedding."""
        manager, embedding_mgr = _setup(tmp_path)

        with patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            return_value=FAKE_EMBEDDING,
        ), patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ):
            memory = await manager.remember(
                content="Some content",
                project_id="test-project",
            )

        original = embedding_mgr.get_embedding(memory.id)

        # Update only importance — should NOT regenerate embedding
        with patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
        ) as mock_gen, patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ):
            manager.update_memory(memory.id, importance=0.9)
            mock_gen.assert_not_called()

        after = embedding_mgr.get_embedding(memory.id)
        assert after.text_hash == original.text_hash

    @pytest.mark.asyncio
    async def test_update_embedding_failure_does_not_block(self, tmp_path) -> None:
        """Embedding failure during update should not block the content update."""
        manager, embedding_mgr = _setup(tmp_path)

        with patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            return_value=FAKE_EMBEDDING,
        ), patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ):
            memory = await manager.remember(
                content="Original",
                project_id="test-project",
            )

        # Update with embedding failure
        with patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ), patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            updated = manager.update_memory(memory.id, content="New content")

        # Content should still be updated
        assert updated.content == "New content"


# =============================================================================
# forget() cascades embedding deletion
# =============================================================================


class TestForgetCascadesEmbedding:
    """Test that deleting a memory cascades to its embedding via FK."""

    @pytest.mark.asyncio
    async def test_forget_cascades_embedding_deletion(self, tmp_path) -> None:
        """Deleting a memory should cascade-delete its embedding via FK constraint."""
        manager, embedding_mgr = _setup(tmp_path)

        with patch(
            "gobby.memory.manager.generate_embedding",
            new_callable=AsyncMock,
            return_value=FAKE_EMBEDDING,
        ), patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ):
            memory = await manager.remember(
                content="Temporary fact",
                project_id="test-project",
            )

        # Verify embedding exists
        assert embedding_mgr.get_embedding(memory.id) is not None

        # Delete memory
        await manager.forget(memory.id)

        # Embedding should be gone (FK cascade)
        assert embedding_mgr.get_embedding(memory.id) is None


# =============================================================================
# Batch reindex embeddings
# =============================================================================


class TestReindexEmbeddings:
    """Test batch embedding reindex operation."""

    @pytest.mark.asyncio
    async def test_reindex_generates_embeddings_for_all(self, tmp_path) -> None:
        """reindex_embeddings() should generate embeddings for all memories."""
        manager, embedding_mgr = _setup(tmp_path)

        # Create memories without embeddings (embedding unavailable)
        with patch(
            "gobby.memory.manager.is_embedding_available", return_value=False
        ):
            m1 = await manager.remember(content="Fact one", project_id="test-project")
            m2 = await manager.remember(content="Fact two", project_id="test-project")
            m3 = await manager.remember(content="Fact three", project_id="test-project")

        # Verify no embeddings yet
        assert embedding_mgr.get_embedding(m1.id) is None
        assert embedding_mgr.get_embedding(m2.id) is None
        assert embedding_mgr.get_embedding(m3.id) is None

        # Reindex with embeddings available
        with patch(
            "gobby.memory.manager.is_embedding_available", return_value=True
        ), patch(
            "gobby.memory.manager.generate_embeddings",
            new_callable=AsyncMock,
            return_value=[FAKE_EMBEDDING, FAKE_EMBEDDING, FAKE_EMBEDDING],
        ):
            result = await manager.reindex_embeddings()

        assert result["success"] is True
        assert result["total_memories"] == 3
        assert result["embeddings_generated"] == 3

        # All should have embeddings now
        assert embedding_mgr.get_embedding(m1.id) is not None
        assert embedding_mgr.get_embedding(m2.id) is not None
        assert embedding_mgr.get_embedding(m3.id) is not None

    @pytest.mark.asyncio
    async def test_reindex_returns_error_when_unavailable(self, tmp_path) -> None:
        """reindex_embeddings() should report error when embeddings unavailable."""
        manager, _ = _setup(tmp_path)

        with patch(
            "gobby.memory.manager.is_embedding_available", return_value=False
        ):
            result = await manager.reindex_embeddings()

        assert result["success"] is False
        assert "unavailable" in result["error"].lower()
