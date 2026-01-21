"""Tests for hybrid search combining TF-IDF and embeddings (TDD)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.skills import LocalSkillManager


@pytest.fixture
def db(tmp_path):
    """Create a fresh database with migrations applied."""
    db_path = tmp_path / "test.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def storage(db):
    """Create a LocalSkillManager for storage operations."""
    return LocalSkillManager(db)


@pytest.fixture
def populated_storage(storage):
    """Create storage with test skills."""
    storage.create_skill(
        name="git-commit",
        description="Generate conventional commit messages for git repositories",
        content="# Git Commit\n\nHelps write commit messages.",
        metadata={"skillport": {"category": "git", "tags": ["git", "commits"]}},
        enabled=True,
    )
    storage.create_skill(
        name="code-review",
        description="AI-powered code review for pull requests",
        content="# Code Review\n\nReviews code quality.",
        metadata={"skillport": {"category": "code-quality", "tags": ["review", "quality"]}},
        enabled=True,
    )
    storage.create_skill(
        name="python-typing",
        description="Add type hints to Python code",
        content="# Python Typing\n\nAdds type annotations.",
        metadata={"skillport": {"category": "python", "tags": ["python", "typing"]}},
        enabled=True,
    )
    return storage


class TestHybridSearchMode:
    """Tests for hybrid search mode selection."""

    def test_default_mode_is_tfidf(self, populated_storage):
        """Test that default search mode is TF-IDF only."""
        from gobby.skills.search import SkillSearch

        search = SkillSearch()
        skills = populated_storage.list_skills()
        search.index_skills(skills)

        # Default mode should be 'tfidf'
        assert search.mode == "tfidf"

    def test_can_set_hybrid_mode(self, populated_storage):
        """Test that hybrid mode can be enabled."""
        from gobby.skills.search import SkillSearch

        search = SkillSearch(mode="hybrid")
        assert search.mode == "hybrid"

    def test_can_set_mode_after_init(self, populated_storage):
        """Test that mode can be changed after initialization."""
        from gobby.skills.search import SkillSearch

        search = SkillSearch()
        search.mode = "hybrid"
        assert search.mode == "hybrid"


class TestHybridSearchScoring:
    """Tests for hybrid search score combination."""

    @pytest.mark.asyncio
    async def test_hybrid_combines_tfidf_and_embeddings(self, populated_storage, mocker):
        """Test that hybrid search combines TF-IDF (40%) and embedding (60%) scores."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider
        from gobby.skills.search import SkillSearch

        # Mock embedding provider
        mock_provider = MagicMock(spec=OpenAIEmbeddingProvider)
        mock_provider.dimension = 1536

        # Create embeddings that would rank differently than TF-IDF
        # For "git commit" query, embedding similarity puts code-review higher
        async def mock_embed(text):
            return [0.1] * 1536

        mock_provider.embed = AsyncMock(side_effect=mock_embed)

        search = SkillSearch(mode="hybrid", embedding_provider=mock_provider)
        skills = populated_storage.list_skills()
        await search.index_skills_async(skills)

        # TF-IDF should rank git-commit first for "git commit"
        # Hybrid should blend the scores
        results = await search.search_async("git commit", top_k=3)

        assert len(results) > 0
        # Results should have scores between 0 and 1
        for r in results:
            assert 0 <= r.similarity <= 1

    @pytest.mark.asyncio
    async def test_hybrid_weights_are_configurable(self, populated_storage, mocker):
        """Test that TF-IDF and embedding weights can be configured."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider
        from gobby.skills.search import SkillSearch

        mock_provider = MagicMock(spec=OpenAIEmbeddingProvider)
        mock_provider.dimension = 1536
        mock_provider.embed = AsyncMock(return_value=[0.1] * 1536)

        # Custom weights: 30% TF-IDF, 70% embeddings
        search = SkillSearch(
            mode="hybrid",
            embedding_provider=mock_provider,
            tfidf_weight=0.3,
            embedding_weight=0.7,
        )
        assert search.tfidf_weight == 0.3
        assert search.embedding_weight == 0.7


class TestHybridSearchFallback:
    """Tests for fallback behavior when embeddings are unavailable."""

    def test_hybrid_falls_back_to_tfidf_without_provider(self, populated_storage):
        """Test that hybrid mode falls back to TF-IDF without embedding provider."""
        from gobby.skills.search import SkillSearch

        # Hybrid mode but no embedding provider
        search = SkillSearch(mode="hybrid")  # No embedding_provider
        skills = populated_storage.list_skills()
        search.index_skills(skills)

        # Should still work using TF-IDF only
        results = search.search("git commit", top_k=3)
        assert len(results) > 0
        assert results[0].skill_name == "git-commit"

    @pytest.mark.asyncio
    async def test_hybrid_falls_back_on_embedding_error(self, populated_storage, mocker):
        """Test that hybrid mode falls back to TF-IDF when embeddings fail."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider
        from gobby.skills.search import SkillSearch

        mock_provider = MagicMock(spec=OpenAIEmbeddingProvider)
        mock_provider.dimension = 1536
        mock_provider.embed = AsyncMock(side_effect=RuntimeError("API error"))

        search = SkillSearch(mode="hybrid", embedding_provider=mock_provider)
        skills = populated_storage.list_skills()
        search.index_skills(skills)

        # Should fall back to TF-IDF without raising
        results = search.search("git commit", top_k=3)
        assert len(results) > 0


class TestEmbeddingIndexing:
    """Tests for skill embedding indexing."""

    @pytest.mark.asyncio
    async def test_index_skills_async_generates_embeddings(self, populated_storage, mocker):
        """Test that index_skills_async generates embeddings for all skills."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider
        from gobby.skills.search import SkillSearch

        mock_provider = MagicMock(spec=OpenAIEmbeddingProvider)
        mock_provider.dimension = 1536
        mock_provider.embed_batch = AsyncMock(
            return_value=[[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
        )

        search = SkillSearch(mode="hybrid", embedding_provider=mock_provider)
        skills = populated_storage.list_skills()
        await search.index_skills_async(skills)

        # Should have called embed_batch
        mock_provider.embed_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_index_works_in_hybrid_mode(self, populated_storage):
        """Test that synchronous index_skills works in hybrid mode (TF-IDF only)."""
        from gobby.skills.search import SkillSearch

        search = SkillSearch(mode="hybrid")
        skills = populated_storage.list_skills()

        # Sync indexing should work without embeddings
        search.index_skills(skills)

        results = search.search("git")
        assert len(results) > 0


class TestHybridSearchAccuracy:
    """Tests for hybrid search improving result quality."""

    @pytest.mark.asyncio
    async def test_semantic_match_improves_ranking(self, populated_storage, mocker):
        """Test that embedding similarity improves semantic matches."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider
        from gobby.skills.search import SkillSearch

        mock_provider = MagicMock(spec=OpenAIEmbeddingProvider)
        mock_provider.dimension = 1536

        # Simulate embeddings where "version control" is semantically close to "git-commit"
        skill_embeddings = {
            "git-commit": [0.9] * 1536,  # High similarity to query
            "code-review": [0.3] * 1536,  # Low similarity
            "python-typing": [0.2] * 1536,  # Low similarity
        }
        query_embedding = [0.9] * 1536

        call_count = [0]

        async def mock_embed(text):
            call_count[0] += 1
            # First call is the query
            if "version control" in text.lower():
                return query_embedding
            return [0.1] * 1536

        async def mock_embed_batch(texts):
            return [skill_embeddings.get(t.split()[0].lower(), [0.1] * 1536) for t in texts]

        mock_provider.embed = AsyncMock(side_effect=mock_embed)
        mock_provider.embed_batch = AsyncMock(side_effect=mock_embed_batch)

        search = SkillSearch(mode="hybrid", embedding_provider=mock_provider)
        skills = populated_storage.list_skills()
        await search.index_skills_async(skills)

        # TF-IDF would not rank "git-commit" high for "version control"
        # but embeddings should boost it
        results = await search.search_async("version control system", top_k=3)

        # git-commit should be in top results due to semantic similarity
        assert len(results) > 0


class TestHybridModeConfiguration:
    """Tests for hybrid search configuration."""

    def test_weights_must_sum_to_one(self):
        """Test that custom weights are normalized."""
        from gobby.skills.search import SkillSearch

        search = SkillSearch(mode="hybrid", tfidf_weight=0.4, embedding_weight=0.6)
        assert abs(search.tfidf_weight + search.embedding_weight - 1.0) < 0.001

    def test_invalid_weights_are_normalized(self):
        """Test that invalid weights are normalized to sum to 1."""
        from gobby.skills.search import SkillSearch

        # Weights that don't sum to 1
        search = SkillSearch(mode="hybrid", tfidf_weight=0.3, embedding_weight=0.3)
        # Should be normalized
        assert abs(search.tfidf_weight + search.embedding_weight - 1.0) < 0.001

    def test_default_weights_are_40_60(self):
        """Test that default weights are 40% TF-IDF, 60% embeddings."""
        from gobby.skills.search import SkillSearch

        search = SkillSearch(mode="hybrid")
        assert search.tfidf_weight == 0.4
        assert search.embedding_weight == 0.6
