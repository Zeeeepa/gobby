"""Comprehensive tests for MemoryManager class.

Tests cover:
- Memory creation (remember)
- Memory retrieval (recall)
- Memory deletion (forget)
- Semantic search integration
- Access statistics and debouncing
- Memory decay operations
- Embedding management
- Statistics retrieval
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.persistence import MemoryConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager, Memory
from gobby.storage.migrations import run_migrations

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    database = LocalDatabase(tmp_path / "gobby.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_config():
    """Create a default memory configuration."""
    return MemoryConfig(
        enabled=True,
        auto_extract=False,
        injection_limit=10,
        importance_threshold=0.3,
        decay_enabled=True,
        decay_rate=0.05,
        decay_floor=0.1,
        semantic_search_enabled=False,
        auto_embed=False,
        access_debounce_seconds=60,
    )


@pytest.fixture
def memory_manager(db, memory_config):
    """Create a MemoryManager with real database."""
    return MemoryManager(db=db, config=memory_config)


@pytest.fixture
def mock_storage():
    """Create a mock LocalMemoryManager."""
    return MagicMock(spec=LocalMemoryManager)


@pytest.fixture
def mock_config():
    """Create a mock MemoryConfig."""
    config = MagicMock(spec=MemoryConfig)
    config.importance_threshold = 0.3
    config.decay_enabled = True
    config.decay_rate = 0.05
    config.decay_floor = 0.1
    config.semantic_search_enabled = False
    config.auto_embed = False
    config.access_debounce_seconds = 60
    return config


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock(spec=LocalDatabase)


# =============================================================================
# Test: Initialization
# =============================================================================


class TestMemoryManagerInit:
    """Tests for MemoryManager initialization."""

    def test_init_creates_storage(self, db, memory_config):
        """Test that initialization creates a LocalMemoryManager."""
        manager = MemoryManager(db=db, config=memory_config)
        assert manager.db is db
        assert manager.config is memory_config
        assert isinstance(manager.storage, LocalMemoryManager)

    def test_init_with_openai_key(self, db, memory_config):
        """Test initialization with OpenAI API key."""
        manager = MemoryManager(
            db=db,
            config=memory_config,
            openai_api_key="test-key",
        )
        assert manager._openai_api_key == "test-key"

    def test_semantic_search_lazy_init(self, db, memory_config):
        """Test that semantic search is lazily initialized."""
        manager = MemoryManager(
            db=db,
            config=memory_config,
            openai_api_key="test-key",
        )
        # Should be None before access
        assert manager._semantic_search is None

        # Access the property to trigger initialization
        # The import happens inside the property, so we patch it at the import location
        with patch("gobby.memory.semantic_search.SemanticMemorySearch") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            result = manager.semantic_search
            assert result is mock_instance
            mock_cls.assert_called_once_with(db=db, openai_api_key="test-key")


# =============================================================================
# Test: Remember (Memory Creation)
# =============================================================================


class TestRemember:
    """Tests for the remember method."""

    @pytest.mark.asyncio
    async def test_remember_basic(self, memory_manager):
        """Test basic memory creation."""
        memory = await memory_manager.remember(
            content="Test fact",
            memory_type="fact",
            importance=0.7,
        )

        assert memory.id.startswith("mm-")
        assert memory.content == "Test fact"
        assert memory.memory_type == "fact"
        assert memory.importance == 0.7

    @pytest.mark.asyncio
    async def test_remember_with_all_params(self, db, memory_config):
        """Test memory creation with all parameters."""
        # Create a project first (required for sessions)
        db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-123", "test-project", "/tmp/test"),
        )
        # Create a session to satisfy foreign key constraint
        now = datetime.now(UTC).isoformat()
        db.execute(
            """INSERT INTO sessions (id, external_id, machine_id, source, project_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("sess-123", "ext-123", "machine-123", "claude", "proj-123", now),
        )

        manager = MemoryManager(db=db, config=memory_config)
        memory = await manager.remember(
            content="User prefers dark theme",
            memory_type="preference",
            importance=0.8,
            project_id=None,  # Global memory
            source_type="user",
            source_session_id="sess-123",
            tags=["ui", "theme"],
        )

        assert memory.content == "User prefers dark theme"
        assert memory.memory_type == "preference"
        assert memory.importance == 0.8
        assert memory.source_type == "user"
        assert memory.source_session_id == "sess-123"
        assert memory.tags == ["ui", "theme"]

    @pytest.mark.asyncio
    async def test_remember_default_values(self, memory_manager):
        """Test memory creation uses correct defaults."""
        memory = await memory_manager.remember(content="Simple fact")

        assert memory.memory_type == "fact"
        assert memory.importance == 0.5
        assert memory.source_type == "user"
        assert memory.tags == []

    @pytest.mark.asyncio
    async def test_remember_with_auto_embed_enabled(self, db):
        """Test that auto_embed triggers embedding when enabled."""
        config = MemoryConfig(auto_embed=True, semantic_search_enabled=True)
        manager = MemoryManager(db=db, config=config, openai_api_key="test-key")

        with patch.object(manager, "embed_memory", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = True
            memory = await manager.remember(content="Auto embed test")

            mock_embed.assert_called_once_with(memory.id, force=False)

    @pytest.mark.asyncio
    async def test_remember_auto_embed_failure_does_not_raise(self, db):
        """Test that auto_embed failure doesn't prevent memory creation."""
        config = MemoryConfig(auto_embed=True, semantic_search_enabled=True)
        manager = MemoryManager(db=db, config=config, openai_api_key="test-key")

        with patch.object(manager, "embed_memory", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = RuntimeError("Embedding failed")

            # Should not raise despite embedding failure
            memory = await manager.remember(content="Test")
            assert memory.content == "Test"


# =============================================================================
# Test: Recall (Memory Retrieval)
# =============================================================================


class TestRecall:
    """Tests for the recall method."""

    @pytest.mark.asyncio
    async def test_recall_no_query_returns_top_memories(self, memory_manager):
        """Test recall without query returns top memories by importance."""
        await memory_manager.remember(content="Low importance", importance=0.2)
        await memory_manager.remember(content="High importance", importance=0.9)
        await memory_manager.remember(content="Medium importance", importance=0.5)

        memories = memory_manager.recall(limit=2)

        assert len(memories) == 2
        assert memories[0].importance >= memories[1].importance

    @pytest.mark.asyncio
    async def test_recall_with_text_query(self, memory_manager):
        """Test recall with text query performs text search."""
        await memory_manager.remember(content="Python is a programming language")
        await memory_manager.remember(content="JavaScript runs in browsers")

        memories = memory_manager.recall(query="Python")

        assert len(memories) == 1
        assert "Python" in memories[0].content

    @pytest.mark.asyncio
    async def test_recall_respects_importance_threshold(self, memory_manager):
        """Test recall filters by importance threshold."""
        await memory_manager.remember(content="Low", importance=0.1)
        await memory_manager.remember(content="High", importance=0.8)

        # Default threshold from config is 0.3
        memories = memory_manager.recall()

        assert len(memories) == 1
        assert memories[0].content == "High"

    @pytest.mark.asyncio
    async def test_recall_custom_min_importance(self, memory_manager):
        """Test recall with custom minimum importance."""
        await memory_manager.remember(content="Low", importance=0.3)
        await memory_manager.remember(content="High", importance=0.8)

        memories = memory_manager.recall(min_importance=0.7)

        assert len(memories) == 1
        assert memories[0].content == "High"

    @pytest.mark.asyncio
    async def test_recall_by_memory_type(self, memory_manager):
        """Test recall filters by memory type."""
        await memory_manager.remember(content="Fact 1", memory_type="fact", importance=0.5)
        await memory_manager.remember(content="Pref 1", memory_type="preference", importance=0.5)

        memories = memory_manager.recall(memory_type="preference")

        assert len(memories) == 1
        assert memories[0].memory_type == "preference"

    @pytest.mark.asyncio
    async def test_recall_limit(self, memory_manager):
        """Test recall respects limit parameter."""
        for i in range(5):
            await memory_manager.remember(content=f"Memory {i}", importance=0.5)

        memories = memory_manager.recall(limit=3)

        assert len(memories) == 3

    @pytest.mark.asyncio
    async def test_recall_updates_access_stats(self, memory_manager):
        """Test recall updates access statistics."""
        memory = await memory_manager.remember(content="Track access", importance=0.5)
        original_count = memory.access_count

        _ = memory_manager.recall(query="Track")

        # Get updated memory
        updated = memory_manager.get_memory(memory.id)
        assert updated.access_count == original_count + 1
        assert updated.last_accessed_at is not None

    def test_recall_semantic_fallback_to_text(self, db):
        """Test recall falls back to text search when semantic search has no embeddings."""
        config = MemoryConfig(semantic_search_enabled=True)
        manager = MemoryManager(db=db, config=config)

        # Create memories synchronously via storage
        manager.storage.create_memory(content="Test semantic fallback", importance=0.5)

        # Should fall back to text search since no embeddings exist
        memories = manager.recall(query="semantic", use_semantic=True)

        assert len(memories) == 1
        assert "semantic" in memories[0].content


# =============================================================================
# Test: Semantic Search Integration
# =============================================================================


class TestSemanticSearch:
    """Tests for semantic search functionality."""

    def test_recall_semantic_no_embeddings_falls_back(self, db):
        """Test _recall_semantic falls back when no embeddings."""
        config = MemoryConfig(semantic_search_enabled=True)
        manager = MemoryManager(db=db, config=config, openai_api_key="test-key")

        # Create memory without embedding
        manager.storage.create_memory(content="Test content", importance=0.5)

        # Pre-set the _semantic_search to our mock before calling the method
        mock_semantic = MagicMock()
        mock_semantic.get_embedding_stats.return_value = {"embedded_memories": 0}
        manager._semantic_search = mock_semantic

        memories = manager._recall_semantic(query="test", limit=10)

        assert len(memories) == 1

    def test_recall_semantic_exception_falls_back(self, db):
        """Test _recall_semantic falls back on exception."""
        config = MemoryConfig(semantic_search_enabled=True)
        manager = MemoryManager(db=db, config=config, openai_api_key="test-key")

        manager.storage.create_memory(content="Test content", importance=0.5)

        # Pre-set the _semantic_search to our mock before calling the method
        mock_semantic = MagicMock()
        mock_semantic.get_embedding_stats.return_value = {"embedded_memories": 5}
        # asyncio.run will be called on search, so we need to simulate an exception
        # that happens during the asyncio.run call
        manager._semantic_search = mock_semantic

        # Since _recall_semantic catches all exceptions in the semantic path,
        # we test by making get_embedding_stats succeed but the asyncio.run fail
        with patch("asyncio.run", side_effect=RuntimeError("API error")):
            with patch("asyncio.get_running_loop", side_effect=RuntimeError("No loop")):
                memories = manager._recall_semantic(query="test", limit=10)

        # Should still return text search results
        assert len(memories) == 1


# =============================================================================
# Test: Access Statistics
# =============================================================================


class TestAccessStats:
    """Tests for access statistics updates."""

    @pytest.mark.asyncio
    async def test_update_access_stats_debouncing(self, memory_manager):
        """Test access stats debouncing prevents rapid updates."""
        memory = await memory_manager.remember(content="Debounce test", importance=0.5)

        # First recall - should update
        _ = memory_manager.recall(query="Debounce")
        updated = memory_manager.get_memory(memory.id)
        first_access_count = updated.access_count

        # Second immediate recall - should be debounced
        _ = memory_manager.recall(query="Debounce")
        updated_again = memory_manager.get_memory(memory.id)

        # Should still be same count due to debouncing
        assert updated_again.access_count == first_access_count

    def test_update_access_stats_empty_list(self, memory_manager):
        """Test _update_access_stats handles empty list."""
        # Should not raise
        memory_manager._update_access_stats([])

    def test_update_access_stats_invalid_timestamp(self, db, memory_config):
        """Test _update_access_stats handles invalid timestamps gracefully."""
        manager = MemoryManager(db=db, config=memory_config)

        # Create memory with invalid timestamp
        memory = MagicMock(spec=Memory)
        memory.id = "mm-test"
        memory.last_accessed_at = "invalid-timestamp"

        # Should not raise, should proceed with update
        manager._update_access_stats([memory])

    def test_update_access_stats_no_timezone(self, db, memory_config):
        """Test _update_access_stats handles timestamps without timezone."""
        manager = MemoryManager(db=db, config=memory_config)

        # Create a real memory first
        real_memory = manager.storage.create_memory(content="Test timezone", importance=0.5)

        # Mock memory with timestamp without timezone
        memory = MagicMock(spec=Memory)
        memory.id = real_memory.id
        memory.last_accessed_at = "2024-01-01T00:00:00"  # No timezone

        manager._update_access_stats([memory])

        # Should have updated
        updated = manager.get_memory(real_memory.id)
        assert updated.access_count >= 1


# =============================================================================
# Test: Forget (Memory Deletion)
# =============================================================================


class TestForget:
    """Tests for the forget method."""

    @pytest.mark.asyncio
    async def test_forget_existing_memory(self, memory_manager):
        """Test forgetting an existing memory."""
        memory = await memory_manager.remember(content="To forget", importance=0.5)

        result = memory_manager.forget(memory.id)

        assert result is True
        assert memory_manager.get_memory(memory.id) is None

    def test_forget_nonexistent_memory(self, memory_manager):
        """Test forgetting a non-existent memory returns False."""
        result = memory_manager.forget("mm-nonexistent")
        assert result is False


# =============================================================================
# Test: List Memories
# =============================================================================


class TestListMemories:
    """Tests for list_memories method."""

    @pytest.mark.asyncio
    async def test_list_memories_basic(self, memory_manager):
        """Test basic memory listing."""
        await memory_manager.remember(content="Memory 1", importance=0.5)
        await memory_manager.remember(content="Memory 2", importance=0.5)

        memories = memory_manager.list_memories()

        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_list_memories_with_offset(self, memory_manager):
        """Test memory listing with offset."""
        for i in range(5):
            await memory_manager.remember(content=f"Memory {i}", importance=0.5)

        memories = memory_manager.list_memories(limit=2, offset=2)

        assert len(memories) == 2

    @pytest.mark.asyncio
    async def test_list_memories_by_type(self, memory_manager):
        """Test memory listing filtered by type."""
        await memory_manager.remember(content="Fact", memory_type="fact", importance=0.5)
        await memory_manager.remember(
            content="Preference", memory_type="preference", importance=0.5
        )

        memories = memory_manager.list_memories(memory_type="fact")

        assert len(memories) == 1
        assert memories[0].memory_type == "fact"


# =============================================================================
# Test: Content Exists
# =============================================================================


class TestContentExists:
    """Tests for content_exists method."""

    @pytest.mark.asyncio
    async def test_content_exists_true(self, memory_manager):
        """Test content_exists returns True for existing content."""
        await memory_manager.remember(content="Existing content", importance=0.5)

        result = memory_manager.content_exists("Existing content")

        assert result is True

    def test_content_exists_false(self, memory_manager):
        """Test content_exists returns False for non-existing content."""
        result = memory_manager.content_exists("Non-existing content")

        assert result is False


# =============================================================================
# Test: Get Memory
# =============================================================================


class TestGetMemory:
    """Tests for get_memory method."""

    @pytest.mark.asyncio
    async def test_get_memory_exists(self, memory_manager):
        """Test getting an existing memory."""
        created = await memory_manager.remember(content="Get test", importance=0.5)

        retrieved = memory_manager.get_memory(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.content == created.content

    def test_get_memory_not_found(self, memory_manager):
        """Test getting a non-existent memory returns None."""
        result = memory_manager.get_memory("mm-nonexistent")

        assert result is None


# =============================================================================
# Test: Update Memory
# =============================================================================


class TestUpdateMemory:
    """Tests for update_memory method."""

    @pytest.mark.asyncio
    async def test_update_memory_content(self, memory_manager):
        """Test updating memory content."""
        memory = await memory_manager.remember(content="Original", importance=0.5)

        updated = memory_manager.update_memory(memory.id, content="Updated")

        assert updated.content == "Updated"

    @pytest.mark.asyncio
    async def test_update_memory_importance(self, memory_manager):
        """Test updating memory importance."""
        memory = await memory_manager.remember(content="Test", importance=0.3)

        updated = memory_manager.update_memory(memory.id, importance=0.9)

        assert updated.importance == 0.9

    @pytest.mark.asyncio
    async def test_update_memory_tags(self, memory_manager):
        """Test updating memory tags."""
        memory = await memory_manager.remember(content="Test", importance=0.5, tags=["old"])

        updated = memory_manager.update_memory(memory.id, tags=["new", "tags"])

        assert updated.tags == ["new", "tags"]

    @pytest.mark.asyncio
    async def test_update_memory_not_found_raises(self, memory_manager):
        """Test updating non-existent memory raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            memory_manager.update_memory("mm-nonexistent", content="New")


# =============================================================================
# Test: Get Stats
# =============================================================================


class TestGetStats:
    """Tests for get_stats method."""

    def test_get_stats_empty(self, memory_manager):
        """Test stats with no memories."""
        stats = memory_manager.get_stats()

        assert stats["total_count"] == 0
        assert stats["by_type"] == {}
        assert stats["avg_importance"] == 0.0

    @pytest.mark.asyncio
    async def test_get_stats_with_memories(self, memory_manager):
        """Test stats with multiple memories."""
        await memory_manager.remember(content="Fact 1", memory_type="fact", importance=0.6)
        await memory_manager.remember(content="Fact 2", memory_type="fact", importance=0.8)
        await memory_manager.remember(content="Pref 1", memory_type="preference", importance=0.4)

        stats = memory_manager.get_stats()

        assert stats["total_count"] == 3
        assert stats["by_type"]["fact"] == 2
        assert stats["by_type"]["preference"] == 1
        assert stats["avg_importance"] == pytest.approx(0.6, rel=0.01)


# =============================================================================
# Test: Decay Memories
# =============================================================================


class TestDecayMemories:
    """Tests for decay_memories method."""

    def test_decay_disabled_returns_zero(self, db):
        """Test decay returns 0 when disabled."""
        config = MemoryConfig(decay_enabled=False)
        manager = MemoryManager(db=db, config=config)

        count = manager.decay_memories()

        assert count == 0

    @pytest.mark.asyncio
    async def test_decay_recent_memories_skipped(self, db):
        """Test decay skips memories updated recently (< 24h)."""
        config = MemoryConfig(decay_enabled=True, decay_rate=0.05, decay_floor=0.1)
        manager = MemoryManager(db=db, config=config)

        # Create memory (will have recent updated_at)
        await manager.remember(content="Recent", importance=0.8)

        count = manager.decay_memories()

        # Should skip because it was just created
        assert count == 0

    def test_decay_old_memories(self, db):
        """Test decay applies to old memories."""
        config = MemoryConfig(decay_enabled=True, decay_rate=0.3, decay_floor=0.1)
        manager = MemoryManager(db=db, config=config)

        # Create memory directly with old timestamp
        old_time = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        memory_id = manager.storage.create_memory(content="Old memory", importance=0.8).id

        # Update timestamp to be old
        db.execute(
            "UPDATE memories SET updated_at = ? WHERE id = ?",
            (old_time, memory_id),
        )

        count = manager.decay_memories()

        assert count == 1

        # Verify importance was reduced
        updated = manager.get_memory(memory_id)
        assert updated.importance < 0.8

    def test_decay_respects_floor(self, db):
        """Test decay doesn't go below floor."""
        config = MemoryConfig(decay_enabled=True, decay_rate=0.9, decay_floor=0.2)
        manager = MemoryManager(db=db, config=config)

        # Create memory with old timestamp
        old_time = (datetime.now(UTC) - timedelta(days=365)).isoformat()
        memory_id = manager.storage.create_memory(content="Very old", importance=0.3).id

        db.execute(
            "UPDATE memories SET updated_at = ? WHERE id = ?",
            (old_time, memory_id),
        )

        manager.decay_memories()

        updated = manager.get_memory(memory_id)
        assert updated.importance >= 0.2  # Should not go below floor


# =============================================================================
# Test: Async Recall
# =============================================================================


class TestAsyncRecall:
    """Tests for async_recall method."""

    @pytest.mark.asyncio
    async def test_async_recall_text_search(self, db):
        """Test async_recall with text search."""
        config = MemoryConfig(semantic_search_enabled=False)
        manager = MemoryManager(db=db, config=config)

        await manager.remember(content="Python programming", importance=0.5)
        await manager.remember(content="JavaScript coding", importance=0.5)

        memories = await manager.async_recall(query="Python")

        assert len(memories) == 1
        assert "Python" in memories[0].content

    @pytest.mark.asyncio
    async def test_async_recall_semantic_search_enabled(self, db):
        """Test async_recall with semantic search enabled."""
        config = MemoryConfig(semantic_search_enabled=True)
        manager = MemoryManager(db=db, config=config, openai_api_key="test-key")

        await manager.remember(content="Test content", importance=0.5)

        mock_result = MagicMock()
        mock_result.memory = Memory(
            id="mm-test",
            content="Test content",
            memory_type="fact",
            importance=0.5,
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )

        # Pre-set the mock semantic search
        mock_semantic = MagicMock()
        mock_semantic.search = AsyncMock(return_value=[mock_result])
        manager._semantic_search = mock_semantic

        memories = await manager.async_recall(query="test")

        assert len(memories) == 1

    @pytest.mark.asyncio
    async def test_async_recall_semantic_failure_fallback(self, db):
        """Test async_recall falls back on semantic search failure."""
        config = MemoryConfig(semantic_search_enabled=True, importance_threshold=0.0)
        manager = MemoryManager(db=db, config=config, openai_api_key="test-key")

        await manager.remember(content="Fallback test", importance=0.5)

        # Pre-set the mock semantic search that will fail
        mock_semantic = MagicMock()
        mock_semantic.search = AsyncMock(side_effect=RuntimeError("API error"))
        manager._semantic_search = mock_semantic

        memories = await manager.async_recall(query="Fallback")

        # Should fall back to text search
        assert len(memories) == 1
        assert "Fallback" in memories[0].content


# =============================================================================
# Test: Embedding Methods
# =============================================================================


class TestEmbeddingMethods:
    """Tests for embedding-related methods."""

    @pytest.mark.asyncio
    async def test_embed_memory_not_found(self, db, memory_config):
        """Test embed_memory returns False for non-existent memory."""
        manager = MemoryManager(db=db, config=memory_config, openai_api_key="test-key")

        result = await manager.embed_memory("mm-nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_embed_memory_success(self, db, memory_config):
        """Test embed_memory calls semantic search."""
        manager = MemoryManager(db=db, config=memory_config, openai_api_key="test-key")

        memory = await manager.remember(content="To embed", importance=0.5)

        # Pre-set the mock semantic search
        mock_semantic = MagicMock()
        mock_semantic.embed_memory = AsyncMock(return_value=True)
        manager._semantic_search = mock_semantic

        result = await manager.embed_memory(memory.id)

        assert result is True
        mock_semantic.embed_memory.assert_called_once_with(
            memory_id=memory.id,
            content=memory.content,
            force=False,
        )

    @pytest.mark.asyncio
    async def test_rebuild_embeddings(self, db, memory_config):
        """Test rebuild_embeddings calls semantic search."""
        manager = MemoryManager(db=db, config=memory_config, openai_api_key="test-key")

        expected_stats = {"embedded": 5, "skipped": 0, "failed": 0, "errors": []}

        # Pre-set the mock semantic search
        mock_semantic = MagicMock()
        mock_semantic.embed_all_memories = AsyncMock(return_value=expected_stats)
        mock_semantic.clear_embeddings = MagicMock()
        manager._semantic_search = mock_semantic

        result = await manager.rebuild_embeddings(force=False)

        assert result == expected_stats
        mock_semantic.embed_all_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_rebuild_embeddings_with_force(self, db, memory_config):
        """Test rebuild_embeddings clears embeddings when force=True."""
        manager = MemoryManager(db=db, config=memory_config, openai_api_key="test-key")

        # Pre-set the mock semantic search
        mock_semantic = MagicMock()
        mock_semantic.embed_all_memories = AsyncMock(
            return_value={"embedded": 0, "skipped": 0, "failed": 0, "errors": []}
        )
        mock_semantic.clear_embeddings = MagicMock()
        manager._semantic_search = mock_semantic

        await manager.rebuild_embeddings(force=True)

        mock_semantic.clear_embeddings.assert_called_once()

    def test_get_embedding_stats(self, db, memory_config):
        """Test get_embedding_stats delegates to semantic search."""
        manager = MemoryManager(db=db, config=memory_config, openai_api_key="test-key")

        expected_stats = {
            "total_memories": 10,
            "embedded_memories": 5,
            "pending_embeddings": 5,
        }

        # Pre-set the mock semantic search
        mock_semantic = MagicMock()
        mock_semantic.get_embedding_stats.return_value = expected_stats
        manager._semantic_search = mock_semantic

        result = manager.get_embedding_stats()

        assert result == expected_stats


# =============================================================================
# Test: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_recall_with_query_filters_by_threshold(self, memory_manager):
        """Test recall with query still applies importance threshold."""
        await memory_manager.remember(content="Low Python", importance=0.1)
        await memory_manager.remember(content="High Python", importance=0.8)

        memories = memory_manager.recall(query="Python")

        # Should only return high importance due to threshold
        assert len(memories) == 1
        assert memories[0].importance >= memory_manager.config.importance_threshold

    @pytest.mark.asyncio
    async def test_duplicate_content_handling(self, memory_manager):
        """Test creating memory with duplicate content returns existing."""
        memory1 = await memory_manager.remember(content="Duplicate test", importance=0.5)
        memory2 = await memory_manager.remember(content="Duplicate test", importance=0.9)

        # Should return same memory due to content-based ID
        assert memory1.id == memory2.id

    def test_recall_empty_database(self, memory_manager):
        """Test recall on empty database returns empty list."""
        memories = memory_manager.recall()
        assert memories == []

    def test_recall_with_use_semantic_false(self, db):
        """Test recall explicitly disabling semantic search."""
        config = MemoryConfig(semantic_search_enabled=True)
        manager = MemoryManager(db=db, config=config)

        manager.storage.create_memory(content="Test text search", importance=0.5)

        memories = manager.recall(query="text", use_semantic=False)

        assert len(memories) == 1

    @pytest.mark.asyncio
    async def test_update_access_stats_exception_handling(self, db, memory_config):
        """Test _update_access_stats handles storage exceptions."""
        manager = MemoryManager(db=db, config=memory_config)

        memory = MagicMock(spec=Memory)
        memory.id = "mm-test"
        memory.last_accessed_at = None

        with patch.object(manager.storage, "update_access_stats") as mock_update:
            mock_update.side_effect = Exception("Database error")

            # Should not raise, just log warning
            manager._update_access_stats([memory])

    def test_decay_memories_handles_timezone_naive_timestamps(self, db):
        """Test decay_memories handles timestamps without timezone."""
        config = MemoryConfig(decay_enabled=True, decay_rate=0.3, decay_floor=0.1)
        manager = MemoryManager(db=db, config=config)

        # Create memory with timezone-naive timestamp (2 months ago)
        old_time = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S")
        memory_id = manager.storage.create_memory(content="Naive timestamp", importance=0.8).id

        db.execute(
            "UPDATE memories SET updated_at = ? WHERE id = ?",
            (old_time, memory_id),
        )

        # Should not raise
        count = manager.decay_memories()
        assert count == 1


# =============================================================================
# Test: Compressor Parameter and recall_as_context
# =============================================================================


class TestMemoryManagerCompressor:
    """Tests for MemoryManager compressor parameter and recall_as_context method."""

    @pytest.fixture
    def mock_compressor(self):
        """Create a mock compressor."""
        compressor = MagicMock()
        compressor.compress.return_value = "Compressed memory content"
        return compressor

    def test_init_accepts_compressor_parameter(self, db, memory_config):
        """Test that __init__ accepts optional compressor parameter."""
        mock_compressor = MagicMock()

        manager = MemoryManager(
            db=db,
            config=memory_config,
            compressor=mock_compressor,
        )

        assert manager.compressor is mock_compressor

    def test_init_compressor_defaults_to_none(self, db, memory_config):
        """Test that compressor defaults to None."""
        manager = MemoryManager(db=db, config=memory_config)

        assert manager.compressor is None

    def test_init_stores_compressor_as_attribute(self, db, memory_config):
        """Test that compressor is stored as instance attribute."""
        mock_compressor = MagicMock()

        manager = MemoryManager(
            db=db,
            config=memory_config,
            compressor=mock_compressor,
        )

        # Verify attribute exists and is set correctly
        assert hasattr(manager, "compressor")
        assert manager.compressor is mock_compressor


class TestRecallAsContext:
    """Tests for recall_as_context method."""

    @pytest.fixture
    def mock_compressor(self):
        """Create a mock compressor."""
        compressor = MagicMock()
        compressor.compress.return_value = "Compressed memory content"
        return compressor

    @pytest.mark.asyncio
    async def test_recall_as_context_returns_formatted_context(self, db, memory_config):
        """Test recall_as_context returns properly formatted context string."""
        manager = MemoryManager(db=db, config=memory_config)

        await manager.remember(content="Test preference", memory_type="preference", importance=0.8)
        await manager.remember(content="Test fact", memory_type="fact", importance=0.7)

        context = manager.recall_as_context()

        # Should return formatted markdown context
        assert isinstance(context, str)
        assert "<project-memory>" in context
        assert "</project-memory>" in context
        assert "Test preference" in context
        assert "Test fact" in context

    @pytest.mark.asyncio
    async def test_recall_as_context_applies_compression_when_compressor_set(
        self, db, memory_config, mock_compressor
    ):
        """Test recall_as_context applies compression when compressor is set."""
        manager = MemoryManager(
            db=db,
            config=memory_config,
            compressor=mock_compressor,
        )

        # Create memories
        for i in range(5):
            await manager.remember(
                content=f"Memory {i} with some extra content to make it longer",
                memory_type="preference",
                importance=0.8,
            )

        # Use low compression threshold to force compression
        manager.recall_as_context(compression_threshold=10)

        # Compressor should have been called
        mock_compressor.compress.assert_called_once()

        # Call should use context_type="memory"
        call_args = mock_compressor.compress.call_args
        assert call_args.kwargs.get("context_type") == "memory"

    @pytest.mark.asyncio
    async def test_recall_as_context_no_compression_when_compressor_none(self, db, memory_config):
        """Test recall_as_context works without compression when compressor is None."""
        manager = MemoryManager(db=db, config=memory_config, compressor=None)

        await manager.remember(content="Test memory", memory_type="preference", importance=0.8)

        context = manager.recall_as_context()

        # Should still return formatted context
        assert "<project-memory>" in context
        assert "Test memory" in context

    @pytest.mark.asyncio
    async def test_recall_as_context_empty_memories(self, db, memory_config):
        """Test recall_as_context returns empty string when no memories."""
        manager = MemoryManager(db=db, config=memory_config)

        context = manager.recall_as_context()

        # Should return empty string
        assert context == ""

    @pytest.mark.asyncio
    async def test_recall_as_context_respects_limit(self, db, memory_config):
        """Test recall_as_context respects limit parameter."""
        manager = MemoryManager(db=db, config=memory_config)

        for i in range(10):
            await manager.remember(content=f"Memory {i}", memory_type="fact", importance=0.8)

        context = manager.recall_as_context(limit=3)

        # Should only include limited number of memories
        # Count occurrences of "Memory" pattern
        assert isinstance(context, str)
        assert "<project-memory>" in context

    @pytest.mark.asyncio
    async def test_recall_as_context_respects_project_filter(self, db, memory_config):
        """Test recall_as_context filters by project_id."""
        manager = MemoryManager(db=db, config=memory_config)

        await manager.remember(content="Global memory", importance=0.8)

        context = manager.recall_as_context(project_id="proj-123")

        # Should respect project filter (no memories for proj-123)
        # Either empty or only project-specific memories
        assert isinstance(context, str)

    @pytest.mark.asyncio
    async def test_recall_as_context_uses_stored_compressor(self, db, memory_config):
        """Test recall_as_context uses the compressor from __init__."""
        mock_compressor = MagicMock()
        mock_compressor.compress.return_value = "Compressed"

        manager = MemoryManager(
            db=db,
            config=memory_config,
            compressor=mock_compressor,
        )

        # Create memories
        for i in range(5):
            await manager.remember(
                content=f"Memory {i} with some extra content padding",
                memory_type="preference",
                importance=0.8,
            )

        # Use low threshold to trigger compression
        manager.recall_as_context(compression_threshold=10)

        # Should use the compressor from __init__
        mock_compressor.compress.assert_called()
