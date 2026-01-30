"""Tests for the SemanticToolSearch module."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.semantic_search import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    SearchResult,
    SemanticToolSearch,
    ToolEmbedding,
    _build_tool_text,
    _compute_text_hash,
    _cosine_similarity,
)
from gobby.storage.database import LocalDatabase
from gobby.storage.mcp import LocalMCPManager

pytestmark = pytest.mark.unit

@pytest.fixture
def semantic_search(temp_db: LocalDatabase) -> SemanticToolSearch:
    """Create a SemanticToolSearch instance with temp database."""
    # Provide a fake API key for testing - actual embedding calls are mocked
    return SemanticToolSearch(temp_db, openai_api_key="sk-test-fake-key")


@pytest.fixture
def sample_tool(
    mcp_manager: LocalMCPManager,
    sample_project: dict,
) -> dict:
    """Create a sample tool for testing."""
    mcp_manager.upsert(
        name="test-server",
        transport="http",
        url="http://localhost:8080",
        project_id=sample_project["id"],
    )
    mcp_manager.cache_tools(
        "test-server",
        [
            {
                "name": "test_tool",
                "description": "A test tool for testing",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results"},
                    },
                },
            }
        ],
        project_id=sample_project["id"],
    )
    tools = mcp_manager.get_cached_tools("test-server", project_id=sample_project["id"])
    return {
        "id": tools[0].id,
        "name": tools[0].name,
        "description": tools[0].description,
        "input_schema": tools[0].input_schema,
        "server_name": "test-server",
        "project_id": sample_project["id"],
    }


class TestTextProcessing:
    """Tests for text processing functions."""

    def test_build_tool_text_basic(self) -> None:
        """Test building tool text with basic inputs."""
        text = _build_tool_text("my_tool", "Does something useful", None)
        assert "Tool: my_tool" in text
        assert "Description: Does something useful" in text

    def test_build_tool_text_with_schema(self) -> None:
        """Test building tool text with input schema."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {"type": "integer"},
            },
        }
        text = _build_tool_text("search", "Search for items", schema)
        assert "Tool: search" in text
        assert "Description: Search for items" in text
        assert "Parameters:" in text
        assert "query (string): Search query" in text
        assert "count (integer)" in text

    def test_build_tool_text_no_description(self) -> None:
        """Test building tool text without description."""
        text = _build_tool_text("simple_tool", None, None)
        assert "Tool: simple_tool" in text
        assert "Description:" not in text

    def test_compute_text_hash(self) -> None:
        """Test text hash computation."""
        hash1 = _compute_text_hash("hello world")
        hash2 = _compute_text_hash("hello world")
        hash3 = _compute_text_hash("different text")

        assert len(hash1) == 16
        assert hash1 == hash2
        assert hash1 != hash3


class TestSemanticToolSearch:
    """Tests for SemanticToolSearch class."""

    def test_init_default_values(self, semantic_search: SemanticToolSearch) -> None:
        """Test initialization with default values."""
        assert semantic_search.embedding_model == DEFAULT_EMBEDDING_MODEL
        assert semantic_search.embedding_dim == DEFAULT_EMBEDDING_DIM

    def test_init_custom_values(self, temp_db: LocalDatabase) -> None:
        """Test initialization with custom values."""
        search = SemanticToolSearch(
            temp_db,
            embedding_model="custom-model",
            embedding_dim=768,
        )
        assert search.embedding_model == "custom-model"
        assert search.embedding_dim == 768

    def test_store_and_get_embedding(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test storing and retrieving an embedding."""
        embedding = [0.1] * 1536  # Mock embedding

        result = semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=embedding,
            text_hash="abcd1234",
        )

        assert isinstance(result, ToolEmbedding)
        assert result.tool_id == sample_tool["id"]
        assert result.server_name == sample_tool["server_name"]
        assert result.embedding_model == DEFAULT_EMBEDDING_MODEL
        assert len(result.embedding) == 1536

        # Retrieve it
        retrieved = semantic_search.get_embedding(sample_tool["id"])
        assert retrieved is not None
        assert retrieved.tool_id == sample_tool["id"]
        # Float precision: 32-bit storage vs 64-bit Python floats
        assert len(retrieved.embedding) == len(embedding)
        assert all(abs(a - b) < 1e-6 for a, b in zip(retrieved.embedding, embedding, strict=True))

    def test_store_embedding_upsert(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test that storing updates existing embedding."""
        embedding1 = [0.1] * 1536
        embedding2 = [0.2] * 1536

        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=embedding1,
            text_hash="hash1",
        )

        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=embedding2,
            text_hash="hash2",
        )

        retrieved = semantic_search.get_embedding(sample_tool["id"])
        assert retrieved is not None
        # Float precision: 32-bit storage vs 64-bit Python floats
        assert len(retrieved.embedding) == len(embedding2)
        assert all(abs(a - b) < 1e-6 for a, b in zip(retrieved.embedding, embedding2, strict=True))
        assert retrieved.text_hash == "hash2"

    def test_get_embedding_nonexistent(self, semantic_search: SemanticToolSearch) -> None:
        """Test getting nonexistent embedding returns None."""
        result = semantic_search.get_embedding("nonexistent-id")
        assert result is None

    def test_get_embeddings_for_project(
        self,
        semantic_search: SemanticToolSearch,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
    ) -> None:
        """Test getting all embeddings for a project."""
        # Create server and cache multiple tools at once
        mcp_manager.upsert(
            name="multi-tool-server",
            transport="http",
            url="http://localhost:8080",
            project_id=sample_project["id"],
        )
        mcp_manager.cache_tools(
            "multi-tool-server",
            [
                {"name": "tool_one", "description": "First tool"},
                {"name": "tool_two", "description": "Second tool"},
            ],
            project_id=sample_project["id"],
        )
        tools = mcp_manager.get_cached_tools("multi-tool-server", project_id=sample_project["id"])

        # Store embeddings
        for tool in tools:
            semantic_search.store_embedding(
                tool_id=tool.id,
                server_name="multi-tool-server",
                project_id=sample_project["id"],
                embedding=[0.1] * 1536,
                text_hash=f"hash-{tool.name}",
            )

        embeddings = semantic_search.get_embeddings_for_project(sample_project["id"])
        assert len(embeddings) == 2

    def test_get_embeddings_for_server(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test getting embeddings for a specific server."""
        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=[0.1] * 1536,
            text_hash="hash",
        )

        embeddings = semantic_search.get_embeddings_for_server(
            "test-server",
            sample_tool["project_id"],
        )
        assert len(embeddings) == 1
        assert embeddings[0].tool_id == sample_tool["id"]

    def test_delete_embedding(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test deleting an embedding."""
        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=[0.1] * 1536,
            text_hash="hash",
        )

        result = semantic_search.delete_embedding(sample_tool["id"])
        assert result is True
        assert semantic_search.get_embedding(sample_tool["id"]) is None

    def test_delete_embedding_nonexistent(self, semantic_search: SemanticToolSearch) -> None:
        """Test deleting nonexistent embedding returns False."""
        result = semantic_search.delete_embedding("nonexistent")
        assert result is False

    def test_delete_embeddings_for_server(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
    ) -> None:
        """Test deleting all embeddings for a server."""
        mcp_manager.cache_tools(
            "test-server",
            [{"name": "tool_a"}, {"name": "tool_b"}],
            project_id=sample_project["id"],
        )
        tools = mcp_manager.get_cached_tools("test-server", project_id=sample_project["id"])

        for tool in tools:
            semantic_search.store_embedding(
                tool_id=tool.id,
                server_name="test-server",
                project_id=sample_project["id"],
                embedding=[0.1] * 1536,
                text_hash=f"hash-{tool.name}",
            )

        count = semantic_search.delete_embeddings_for_server(
            "test-server",
            sample_project["id"],
        )
        assert count == 2
        assert len(semantic_search.get_embeddings_for_project(sample_project["id"])) == 0

    def test_needs_reembedding_new_tool(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test that new tool needs embedding."""
        result = semantic_search.needs_reembedding(
            tool_id=sample_tool["id"],
            name=sample_tool["name"],
            description=sample_tool["description"],
            input_schema=sample_tool["input_schema"],
        )
        assert result is True

    def test_needs_reembedding_unchanged(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test that unchanged tool doesn't need reembedding."""
        # Build the text and hash
        text = SemanticToolSearch.build_tool_text(
            sample_tool["name"],
            sample_tool["description"],
            sample_tool["input_schema"],
        )
        text_hash = SemanticToolSearch.compute_text_hash(text)

        # Store with correct hash
        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=[0.1] * 1536,
            text_hash=text_hash,
        )

        result = semantic_search.needs_reembedding(
            tool_id=sample_tool["id"],
            name=sample_tool["name"],
            description=sample_tool["description"],
            input_schema=sample_tool["input_schema"],
        )
        assert result is False

    def test_needs_reembedding_changed(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test that changed tool needs reembedding."""
        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=[0.1] * 1536,
            text_hash="old-hash",
        )

        result = semantic_search.needs_reembedding(
            tool_id=sample_tool["id"],
            name=sample_tool["name"],
            description="New description",
            input_schema=sample_tool["input_schema"],
        )
        assert result is True

    def test_get_embedding_stats(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test getting embedding statistics."""
        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=[0.1] * 1536,
            text_hash="hash",
        )

        stats = semantic_search.get_embedding_stats(sample_tool["project_id"])
        assert stats["total_embeddings"] == 1
        assert stats["embedding_model"] == DEFAULT_EMBEDDING_MODEL
        assert stats["embedding_dim"] == DEFAULT_EMBEDDING_DIM
        assert "test-server" in stats["by_server"]
        assert stats["by_server"]["test-server"] == 1

    def test_get_embedding_stats_all(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test getting stats without project filter."""
        semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=[0.1] * 1536,
            text_hash="hash",
        )

        stats = semantic_search.get_embedding_stats()
        assert stats["total_embeddings"] == 1


class TestToolEmbedding:
    """Tests for ToolEmbedding dataclass."""

    def test_to_dict(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
    ) -> None:
        """Test converting ToolEmbedding to dictionary."""
        embedding = semantic_search.store_embedding(
            tool_id=sample_tool["id"],
            server_name=sample_tool["server_name"],
            project_id=sample_tool["project_id"],
            embedding=[0.1] * 1536,
            text_hash="hash123",
        )

        d = embedding.to_dict()
        assert d["tool_id"] == sample_tool["id"]
        assert d["server_name"] == sample_tool["server_name"]
        assert d["text_hash"] == "hash123"
        # Embedding should not be in dict (too large for serialization)
        assert "embedding" not in d


class TestEmbeddingGeneration:
    """Tests for embedding generation methods."""

    @pytest.fixture
    def mock_litellm_response(self):
        """Create a mock litellm embedding response."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1] * 1536}]
        return mock_response

    @pytest.mark.asyncio
    async def test_embed_text(
        self,
        semantic_search: SemanticToolSearch,
        mock_litellm_response: MagicMock,
    ):
        """Test generating embedding for text."""
        with patch("litellm.aembedding", new_callable=AsyncMock) as mock_aembedding:
            mock_aembedding.return_value = mock_litellm_response

            result = await semantic_search.embed_text("test text")

            assert len(result) == 1536
            mock_aembedding.assert_called_once_with(
                model=DEFAULT_EMBEDDING_MODEL,
                input=["test text"],
                api_key=ANY,  # API key from env or ~/.codex/auth.json
            )

    @pytest.mark.asyncio
    async def test_embed_text_error(
        self,
        semantic_search: SemanticToolSearch,
    ):
        """Test embed_text raises RuntimeError on failure."""
        with patch("litellm.aembedding", new_callable=AsyncMock) as mock_aembedding:
            mock_aembedding.side_effect = Exception("API error")

            with pytest.raises(RuntimeError, match="Embedding generation failed"):
                await semantic_search.embed_text("test text")

    @pytest.mark.asyncio
    async def test_embed_tool(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
        mock_litellm_response: MagicMock,
    ):
        """Test generating and storing embedding for a tool."""
        with patch("litellm.aembedding", new_callable=AsyncMock) as mock_aembedding:
            mock_aembedding.return_value = mock_litellm_response

            result = await semantic_search.embed_tool(
                tool_id=sample_tool["id"],
                name=sample_tool["name"],
                description=sample_tool["description"],
                input_schema=sample_tool["input_schema"],
                server_name=sample_tool["server_name"],
                project_id=sample_tool["project_id"],
            )

            assert result is not None
            assert result.tool_id == sample_tool["id"]
            assert len(result.embedding) == 1536

    @pytest.mark.asyncio
    async def test_embed_tool_skips_if_unchanged(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
        mock_litellm_response: MagicMock,
    ):
        """Test that embed_tool skips if content unchanged."""
        with patch("litellm.aembedding", new_callable=AsyncMock) as mock_aembedding:
            mock_aembedding.return_value = mock_litellm_response

            # First call - should embed
            result1 = await semantic_search.embed_tool(
                tool_id=sample_tool["id"],
                name=sample_tool["name"],
                description=sample_tool["description"],
                input_schema=sample_tool["input_schema"],
                server_name=sample_tool["server_name"],
                project_id=sample_tool["project_id"],
            )
            assert result1 is not None

            # Second call - should skip (returns None)
            result2 = await semantic_search.embed_tool(
                tool_id=sample_tool["id"],
                name=sample_tool["name"],
                description=sample_tool["description"],
                input_schema=sample_tool["input_schema"],
                server_name=sample_tool["server_name"],
                project_id=sample_tool["project_id"],
            )
            assert result2 is None

            # Should only have called API once
            assert mock_aembedding.call_count == 1

    @pytest.mark.asyncio
    async def test_embed_tool_force_reembed(
        self,
        semantic_search: SemanticToolSearch,
        sample_tool: dict,
        mock_litellm_response: MagicMock,
    ):
        """Test force re-embedding even if unchanged."""
        with patch("litellm.aembedding", new_callable=AsyncMock) as mock_aembedding:
            mock_aembedding.return_value = mock_litellm_response

            # First call
            await semantic_search.embed_tool(
                tool_id=sample_tool["id"],
                name=sample_tool["name"],
                description=sample_tool["description"],
                input_schema=sample_tool["input_schema"],
                server_name=sample_tool["server_name"],
                project_id=sample_tool["project_id"],
            )

            # Second call with force=True
            result = await semantic_search.embed_tool(
                tool_id=sample_tool["id"],
                name=sample_tool["name"],
                description=sample_tool["description"],
                input_schema=sample_tool["input_schema"],
                server_name=sample_tool["server_name"],
                project_id=sample_tool["project_id"],
                force=True,
            )
            assert result is not None

            # Should have called API twice
            assert mock_aembedding.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_all_tools(
        self,
        semantic_search: SemanticToolSearch,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
        mock_litellm_response: MagicMock,
    ):
        """Test embedding all tools for a project."""
        # Create server with multiple tools
        mcp_manager.upsert(
            name="embed-server",
            transport="http",
            url="http://localhost:8080",
            project_id=sample_project["id"],
        )
        mcp_manager.cache_tools(
            "embed-server",
            [
                {"name": "tool_a", "description": "Tool A"},
                {"name": "tool_b", "description": "Tool B"},
            ],
            project_id=sample_project["id"],
        )

        with patch("litellm.aembedding", new_callable=AsyncMock) as mock_aembedding:
            mock_aembedding.return_value = mock_litellm_response

            stats = await semantic_search.embed_all_tools(
                project_id=sample_project["id"],
                mcp_manager=mcp_manager,
            )

            assert stats["embedded"] == 2
            assert stats["skipped"] == 0
            assert stats["failed"] == 0
            assert "embed-server" in stats["by_server"]
            assert stats["by_server"]["embed-server"]["embedded"] == 2

    @pytest.mark.asyncio
    async def test_embed_all_tools_handles_errors(
        self,
        semantic_search: SemanticToolSearch,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
    ):
        """Test that embed_all_tools handles errors gracefully."""
        mcp_manager.upsert(
            name="error-server",
            transport="http",
            url="http://localhost:8080",
            project_id=sample_project["id"],
        )
        mcp_manager.cache_tools(
            "error-server",
            [{"name": "failing_tool", "description": "Will fail"}],
            project_id=sample_project["id"],
        )

        with patch("litellm.aembedding", new_callable=AsyncMock) as mock_aembedding:
            mock_aembedding.side_effect = Exception("API error")

            stats = await semantic_search.embed_all_tools(
                project_id=sample_project["id"],
                mcp_manager=mcp_manager,
            )

            assert stats["embedded"] == 0
            assert stats["failed"] == 1
            assert len(stats["errors"]) == 1
            assert "API error" in stats["errors"][0]


class TestCosineSimilarity:
    """Tests for cosine similarity function."""

    def test_identical_vectors(self) -> None:
        """Test that identical vectors have similarity 1.0."""
        vec = [0.5, 0.5, 0.5]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_opposite_vectors(self) -> None:
        """Test that opposite vectors have similarity -1.0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(vec1, vec2) - (-1.0)) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        """Test that orthogonal vectors have similarity 0.0."""
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        assert abs(_cosine_similarity(vec1, vec2)) < 1e-6

    def test_dimension_mismatch_raises(self) -> None:
        """Test that dimension mismatch raises ValueError."""
        vec1 = [1.0, 2.0]
        vec2 = [1.0, 2.0, 3.0]
        with pytest.raises(ValueError, match="dimension mismatch"):
            _cosine_similarity(vec1, vec2)

    def test_zero_vector(self) -> None:
        """Test that zero vector returns 0.0."""
        vec1 = [0.0, 0.0]
        vec2 = [1.0, 1.0]
        assert _cosine_similarity(vec1, vec2) == 0.0


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_to_dict(self) -> None:
        """Test converting SearchResult to dictionary."""
        result = SearchResult(
            tool_id="tool-123",
            server_name="test-server",
            tool_name="my_tool",
            description="A test tool",
            similarity=0.85678,
            embedding_id=1,
        )
        d = result.to_dict()
        assert d["tool_id"] == "tool-123"
        assert d["server_name"] == "test-server"
        assert d["tool_name"] == "my_tool"
        assert d["description"] == "A test tool"
        assert d["similarity"] == 0.8568  # Rounded to 4 decimal places
        assert "embedding_id" not in d  # Not included in dict


class TestSearchTools:
    """Tests for search_tools method."""

    @pytest.fixture
    def mock_litellm_response(self):
        """Create a mock litellm embedding response."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1] * 1536}]
        return mock_response

    @pytest.mark.asyncio
    async def test_search_tools_basic(
        self,
        semantic_search: SemanticToolSearch,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
    ):
        """Test basic tool search."""
        # Create server and tools
        mcp_manager.upsert(
            name="search-server",
            transport="http",
            url="http://localhost:8080",
            project_id=sample_project["id"],
        )
        mcp_manager.cache_tools(
            "search-server",
            [
                {"name": "search_tool", "description": "Search for things"},
                {"name": "create_tool", "description": "Create new items"},
            ],
            project_id=sample_project["id"],
        )

        # Store embeddings with different vectors to get different similarities
        tools = mcp_manager.get_cached_tools("search-server", project_id=sample_project["id"])
        # search_tool gets vector closer to query
        semantic_search.store_embedding(
            tool_id=tools[0].id,
            server_name="search-server",
            project_id=sample_project["id"],
            embedding=[0.9] * 1536,  # Similar to query
            text_hash="hash1",
        )
        # create_tool gets different vector
        semantic_search.store_embedding(
            tool_id=tools[1].id,
            server_name="search-server",
            project_id=sample_project["id"],
            embedding=[0.1] * 1536,  # Less similar
            text_hash="hash2",
        )

        # Mock embed_text to return query embedding
        with patch.object(semantic_search, "embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.9] * 1536  # Query embedding

            results = await semantic_search.search_tools(
                query="find something",
                project_id=sample_project["id"],
            )

            assert len(results) == 2
            # search_tool should be first (higher similarity)
            assert results[0].tool_name == "search_tool"
            assert results[0].similarity > results[1].similarity

    @pytest.mark.asyncio
    async def test_search_tools_with_top_k(
        self,
        semantic_search: SemanticToolSearch,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
    ):
        """Test search with top_k limit."""
        mcp_manager.upsert(
            name="topk-server",
            transport="http",
            url="http://localhost:8080",
            project_id=sample_project["id"],
        )
        mcp_manager.cache_tools(
            "topk-server",
            [
                {"name": "tool_a"},
                {"name": "tool_b"},
                {"name": "tool_c"},
            ],
            project_id=sample_project["id"],
        )

        tools = mcp_manager.get_cached_tools("topk-server", project_id=sample_project["id"])
        for tool in tools:
            semantic_search.store_embedding(
                tool_id=tool.id,
                server_name="topk-server",
                project_id=sample_project["id"],
                embedding=[0.5] * 1536,
                text_hash=f"hash-{tool.name}",
            )

        with patch.object(semantic_search, "embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 1536

            results = await semantic_search.search_tools(
                query="test",
                project_id=sample_project["id"],
                top_k=2,
            )

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_tools_with_min_similarity(
        self,
        semantic_search: SemanticToolSearch,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
    ):
        """Test search with minimum similarity threshold."""
        mcp_manager.upsert(
            name="minsim-server",
            transport="http",
            url="http://localhost:8080",
            project_id=sample_project["id"],
        )
        mcp_manager.cache_tools(
            "minsim-server",
            [
                {"name": "relevant_tool"},
                {"name": "irrelevant_tool"},
            ],
            project_id=sample_project["id"],
        )

        tools = mcp_manager.get_cached_tools("minsim-server", project_id=sample_project["id"])
        tool_by_name = {t.name: t for t in tools}

        # High similarity tool
        semantic_search.store_embedding(
            tool_id=tool_by_name["relevant_tool"].id,
            server_name="minsim-server",
            project_id=sample_project["id"],
            embedding=[0.9] * 1536,
            text_hash="hash1",
        )
        # Low similarity tool (orthogonal-ish)
        semantic_search.store_embedding(
            tool_id=tool_by_name["irrelevant_tool"].id,
            server_name="minsim-server",
            project_id=sample_project["id"],
            embedding=[-0.5] * 1536,
            text_hash="hash2",
        )

        with patch.object(semantic_search, "embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.9] * 1536

            results = await semantic_search.search_tools(
                query="test",
                project_id=sample_project["id"],
                min_similarity=0.5,
            )

            # Only the relevant tool should pass the threshold
            assert len(results) == 1
            assert results[0].tool_name == "relevant_tool"

    @pytest.mark.asyncio
    async def test_search_tools_with_server_filter(
        self,
        semantic_search: SemanticToolSearch,
        mcp_manager: LocalMCPManager,
        sample_project: dict,
    ):
        """Test search with server filter."""
        # Create two servers
        mcp_manager.upsert(
            name="server-a",
            transport="http",
            url="http://localhost:8080",
            project_id=sample_project["id"],
        )
        mcp_manager.upsert(
            name="server-b",
            transport="http",
            url="http://localhost:8081",
            project_id=sample_project["id"],
        )

        mcp_manager.cache_tools("server-a", [{"name": "tool_a"}], project_id=sample_project["id"])
        mcp_manager.cache_tools("server-b", [{"name": "tool_b"}], project_id=sample_project["id"])

        tools_a = mcp_manager.get_cached_tools("server-a", project_id=sample_project["id"])
        tools_b = mcp_manager.get_cached_tools("server-b", project_id=sample_project["id"])

        for tool in tools_a:
            semantic_search.store_embedding(
                tool_id=tool.id,
                server_name="server-a",
                project_id=sample_project["id"],
                embedding=[0.5] * 1536,
                text_hash="hash-a",
            )
        for tool in tools_b:
            semantic_search.store_embedding(
                tool_id=tool.id,
                server_name="server-b",
                project_id=sample_project["id"],
                embedding=[0.5] * 1536,
                text_hash="hash-b",
            )

        with patch.object(semantic_search, "embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 1536

            results = await semantic_search.search_tools(
                query="test",
                project_id=sample_project["id"],
                server_filter="server-a",
            )

            assert len(results) == 1
            assert results[0].server_name == "server-a"

    @pytest.mark.asyncio
    async def test_search_tools_no_embeddings(
        self,
        semantic_search: SemanticToolSearch,
        sample_project: dict,
    ):
        """Test search returns empty when no embeddings exist."""
        with patch.object(semantic_search, "embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 1536

            results = await semantic_search.search_tools(
                query="test",
                project_id=sample_project["id"],
            )

            assert results == []
