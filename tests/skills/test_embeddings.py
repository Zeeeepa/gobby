"""Tests for EmbeddingProvider abstraction (TDD - written before implementation)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEmbeddingProviderProtocol:
    """Tests for EmbeddingProvider Protocol definition."""

    def test_protocol_defines_embed_method(self):
        """Test that Protocol defines embed() method."""
        from gobby.skills.embeddings import EmbeddingProvider

        # Protocol should have embed method
        assert hasattr(EmbeddingProvider, "embed")
        # Should be async
        assert hasattr(EmbeddingProvider.embed, "__call__")

    def test_protocol_defines_embed_batch_method(self):
        """Test that Protocol defines embed_batch() method."""
        from gobby.skills.embeddings import EmbeddingProvider

        assert hasattr(EmbeddingProvider, "embed_batch")

    def test_protocol_defines_dimension_property(self):
        """Test that Protocol defines dimension property."""
        from gobby.skills.embeddings import EmbeddingProvider

        # Should have dimension as an attribute
        assert "dimension" in dir(EmbeddingProvider)


class TestOpenAIEmbeddingProvider:
    """Tests for OpenAI embedding provider implementation."""

    def test_provider_has_correct_dimension(self):
        """Test that OpenAI provider reports correct dimension."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider()
        # text-embedding-3-small has 1536 dimensions
        assert provider.dimension == 1536

    def test_provider_accepts_custom_dimension(self):
        """Test that provider can be configured with custom dimension."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(model="text-embedding-3-large", dimension=3072)
        assert provider.dimension == 3072

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self, mocker):
        """Test that embed() returns a vector of floats."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider

        # Mock litellm before it gets imported
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1] * 1536}]
        mock_litellm = MagicMock()
        mock_litellm.aembedding = AsyncMock(return_value=mock_response)
        mocker.patch.dict("sys.modules", {"litellm": mock_litellm})

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        result = await provider.embed("test text")

        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(x, (int, float)) for x in result)

    @pytest.mark.asyncio
    async def test_embed_batch_returns_vectors(self, mocker):
        """Test that embed_batch() returns list of vectors."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider

        mock_response = MagicMock()
        mock_response.data = [
            {"embedding": [0.1] * 1536},
            {"embedding": [0.2] * 1536},
        ]
        mock_litellm = MagicMock()
        mock_litellm.aembedding = AsyncMock(return_value=mock_response)
        mocker.patch.dict("sys.modules", {"litellm": mock_litellm})

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        result = await provider.embed_batch(["text 1", "text 2"])

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(len(vec) == 1536 for vec in result)

    @pytest.mark.asyncio
    async def test_embed_raises_without_api_key(self):
        """Test that embed() raises error when no API key is available."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider()  # No api_key

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                await provider.embed("test")

    def test_provider_implements_protocol(self):
        """Test that OpenAIEmbeddingProvider implements EmbeddingProvider."""
        from gobby.skills.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(api_key="test")

        # Structural subtyping - has all required methods
        assert hasattr(provider, "embed")
        assert hasattr(provider, "embed_batch")
        assert hasattr(provider, "dimension")


class TestEmbeddingProviderFallback:
    """Tests for graceful fallback when provider is unavailable."""

    def test_get_provider_returns_none_without_api_key(self):
        """Test that get_embedding_provider returns None when not configured."""
        from gobby.skills.embeddings import get_embedding_provider

        with patch.dict("os.environ", {}, clear=True):
            provider = get_embedding_provider()
            assert provider is None

    def test_get_provider_returns_provider_with_api_key(self):
        """Test that get_embedding_provider returns provider when configured."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider, get_embedding_provider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            provider = get_embedding_provider()
            assert provider is not None
            assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_get_provider_uses_config_api_key(self):
        """Test that get_embedding_provider can use explicit API key."""
        from gobby.skills.embeddings import OpenAIEmbeddingProvider, get_embedding_provider

        provider = get_embedding_provider(api_key="explicit-key")
        assert provider is not None
        assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_is_available_returns_false_without_api_key(self):
        """Test is_available() returns False when not configured."""
        from gobby.skills.embeddings import is_embedding_available

        with patch.dict("os.environ", {}, clear=True):
            assert is_embedding_available() is False

    def test_is_available_returns_true_with_api_key(self):
        """Test is_available() returns True when configured."""
        from gobby.skills.embeddings import is_embedding_available

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            assert is_embedding_available() is True


class TestSemanticSkillSearch:
    """Tests for semantic skill search integration (optional enhancement)."""

    def test_search_falls_back_to_tfidf_without_embeddings(self):
        """Test that search gracefully falls back to TF-IDF when no embeddings."""
        from gobby.skills.search import SkillSearch

        # Regular SkillSearch should work without any embedding provider
        search = SkillSearch()
        assert search is not None
        # Should be able to search (empty results since no skills indexed)
        results = search.search("test query")
        assert results == []
