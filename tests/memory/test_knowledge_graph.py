"""Tests for KnowledgeGraphService."""

from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.memory.neo4j_client import Neo4jConnectionError
from gobby.memory.services.knowledge_graph import (
    Entity,
    KnowledgeGraphService,
    Relationship,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_neo4j() -> AsyncMock:
    """Mock Neo4jClient."""
    client = AsyncMock()
    client.merge_node = AsyncMock(return_value=[])
    client.merge_relationship = AsyncMock(return_value=[])
    client.set_node_vector = AsyncMock(return_value=None)
    client.get_entity_graph = AsyncMock(return_value={"entities": [], "relationships": []})
    client.get_entity_neighbors = AsyncMock(return_value={"entities": [], "relationships": []})
    client.query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Mock LLMProvider."""
    return AsyncMock()


@pytest.fixture
def mock_embed_fn() -> AsyncMock:
    """Mock embedding function."""
    return AsyncMock(return_value=[0.1, 0.2, 0.3])


@pytest.fixture
def mock_prompt_loader() -> MagicMock:
    """Mock PromptLoader."""
    loader = MagicMock()
    loader.render = MagicMock(return_value="rendered prompt")
    return loader


@pytest.fixture
def service(
    mock_neo4j: AsyncMock,
    mock_llm: AsyncMock,
    mock_embed_fn: AsyncMock,
    mock_prompt_loader: MagicMock,
) -> KnowledgeGraphService:
    """Create a KnowledgeGraphService with all mocked deps."""
    return KnowledgeGraphService(
        neo4j_client=mock_neo4j,
        llm_provider=mock_llm,
        embed_fn=mock_embed_fn,
        prompt_loader=mock_prompt_loader,
    )


# ===========================================================================
# Dataclass tests
# ===========================================================================


class TestEntity:
    """Tests for Entity dataclass."""

    def test_entity_creation(self) -> None:
        """Entity stores name and entity_type."""
        e = Entity(name="Josh", entity_type="person")
        assert e.name == "Josh"
        assert e.entity_type == "person"

    def test_entity_asdict(self) -> None:
        """Entity can be serialized to dict."""
        e = Entity(name="Python", entity_type="tool")
        d = asdict(e)
        assert d == {"name": "Python", "entity_type": "tool"}


class TestRelationship:
    """Tests for Relationship dataclass."""

    def test_relationship_creation(self) -> None:
        """Relationship stores source, target, relationship."""
        r = Relationship(source="Josh", target="Gobby", relationship="works_on")
        assert r.source == "Josh"
        assert r.target == "Gobby"
        assert r.relationship == "works_on"

    def test_relationship_asdict(self) -> None:
        """Relationship can be serialized to dict."""
        r = Relationship(source="A", target="B", relationship="uses")
        d = asdict(r)
        assert d == {"source": "A", "target": "B", "relationship": "uses"}


# ===========================================================================
# Write path: add_to_graph
# ===========================================================================


class TestAddToGraph:
    """Tests for KnowledgeGraphService.add_to_graph()."""

    async def test_add_to_graph_extracts_entities(
        self,
        service: KnowledgeGraphService,
        mock_llm: AsyncMock,
        mock_prompt_loader: MagicMock,
    ) -> None:
        """add_to_graph calls LLM to extract entities from content."""
        mock_llm.generate_json = AsyncMock(
            side_effect=[
                # Entity extraction
                {"entities": [{"entity": "Josh", "entity_type": "person"}]},
                # Relationship extraction
                {"relations": []},
                # Delete relations (existing relations empty)
                {"relations_to_delete": []},
            ]
        )

        await service.add_to_graph("Josh works at Anthropic")

        # Verify entity extraction prompt was rendered
        mock_prompt_loader.render.assert_any_call(
            "memory/extract_entities",
            {"content": "Josh works at Anthropic"},
        )

    async def test_add_to_graph_extracts_relationships(
        self,
        service: KnowledgeGraphService,
        mock_llm: AsyncMock,
        mock_prompt_loader: MagicMock,
    ) -> None:
        """add_to_graph calls LLM to extract relationships between entities."""
        entities = [{"entity": "Josh", "entity_type": "person"}]
        mock_llm.generate_json = AsyncMock(
            side_effect=[
                {"entities": entities},
                {
                    "relations": [
                        {"source": "Josh", "relationship": "works_on", "destination": "Gobby"}
                    ]
                },
                {"relations_to_delete": []},
            ]
        )

        await service.add_to_graph("Josh works on Gobby")

        mock_prompt_loader.render.assert_any_call(
            "memory/extract_relations",
            {"content": "Josh works on Gobby", "entities": json.dumps(entities)},
        )

    async def test_add_to_graph_merges_nodes(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """add_to_graph calls merge_node for each extracted entity."""
        mock_llm.generate_json = AsyncMock(
            side_effect=[
                {
                    "entities": [
                        {"entity": "Josh", "entity_type": "person"},
                        {"entity": "Python", "entity_type": "tool"},
                    ]
                },
                {"relations": []},
                {"relations_to_delete": []},
            ]
        )

        await service.add_to_graph("Josh uses Python")

        assert mock_neo4j.merge_node.call_count == 2
        # Check first call was for Josh
        first_call = mock_neo4j.merge_node.call_args_list[0]
        assert first_call.kwargs["name"] == "Josh"

    async def test_add_to_graph_merges_relationships(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """add_to_graph calls merge_relationship for each extracted relationship."""
        mock_llm.generate_json = AsyncMock(
            side_effect=[
                {
                    "entities": [
                        {"entity": "Josh", "entity_type": "person"},
                        {"entity": "Python", "entity_type": "tool"},
                    ]
                },
                {
                    "relations": [
                        {"source": "Josh", "relationship": "uses", "destination": "Python"},
                    ]
                },
                {"relations_to_delete": []},
            ]
        )

        await service.add_to_graph("Josh uses Python")

        mock_neo4j.merge_relationship.assert_called_once()
        call_kwargs = mock_neo4j.merge_relationship.call_args.kwargs
        assert call_kwargs["source"] == "Josh"
        assert call_kwargs["target"] == "Python"
        assert call_kwargs["rel_type"] == "uses"

    async def test_add_to_graph_sets_embeddings(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
        mock_embed_fn: AsyncMock,
    ) -> None:
        """add_to_graph sets embedding vectors on nodes."""
        mock_llm.generate_json = AsyncMock(
            side_effect=[
                {"entities": [{"entity": "Josh", "entity_type": "person"}]},
                {"relations": []},
                {"relations_to_delete": []},
            ]
        )

        await service.add_to_graph("Josh is a person")

        mock_embed_fn.assert_called()
        mock_neo4j.set_node_vector.assert_called_once()

    async def test_add_to_graph_deletes_outdated_relations(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """add_to_graph deletes outdated relationships identified by LLM."""
        # Existing relations in Neo4j
        mock_neo4j.query = AsyncMock(
            return_value=[
                {"source": "Josh", "rel_type": "uses", "target": "Python 3.12"},
            ]
        )

        mock_llm.generate_json = AsyncMock(
            side_effect=[
                {
                    "entities": [
                        {"entity": "Josh", "entity_type": "person"},
                        {"entity": "Python 3.13", "entity_type": "tool"},
                    ]
                },
                {
                    "relations": [
                        {"source": "Josh", "relationship": "uses", "destination": "Python 3.13"},
                    ]
                },
                {
                    "relations_to_delete": [
                        {"source": "Josh", "relationship": "uses", "destination": "Python 3.12"},
                    ]
                },
            ]
        )

        await service.add_to_graph("Josh uses Python 3.13")

        # Should have called query to delete the outdated relation
        delete_calls = [c for c in mock_neo4j.query.call_args_list if "DELETE" in str(c)]
        assert len(delete_calls) >= 1

    async def test_add_to_graph_no_entities_returns_early(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """add_to_graph returns early when no entities are extracted."""
        mock_llm.generate_json = AsyncMock(
            return_value={"entities": []},
        )

        await service.add_to_graph("nothing useful")

        mock_neo4j.merge_node.assert_not_called()


# ===========================================================================
# Read path
# ===========================================================================


class TestGetEntityGraph:
    """Tests for get_entity_graph read method."""

    async def test_get_entity_graph_delegates_to_client(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
    ) -> None:
        """get_entity_graph delegates to neo4j_client."""
        expected = {"entities": [{"name": "Josh"}], "relationships": []}
        mock_neo4j.get_entity_graph = AsyncMock(return_value=expected)

        result = await service.get_entity_graph(limit=100)

        assert result == expected
        mock_neo4j.get_entity_graph.assert_called_once_with(limit=100)


class TestGetEntityNeighbors:
    """Tests for get_entity_neighbors read method."""

    async def test_get_entity_neighbors_delegates(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
    ) -> None:
        """get_entity_neighbors delegates to neo4j_client."""
        expected = {"entities": [{"name": "Python"}], "relationships": []}
        mock_neo4j.get_entity_neighbors = AsyncMock(return_value=expected)

        result = await service.get_entity_neighbors("Josh")

        assert result == expected
        mock_neo4j.get_entity_neighbors.assert_called_once_with("Josh")


class TestSearchGraph:
    """Tests for search_graph read method."""

    async def test_search_graph_returns_matching_entities(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
    ) -> None:
        """search_graph queries Neo4j for entities matching the query."""
        mock_neo4j.query = AsyncMock(
            return_value=[
                {"name": "Python", "labels": ["Tool"], "score": 0.9},
            ]
        )

        result = await service.search_graph("programming language", limit=5)

        assert len(result) >= 1
        mock_neo4j.query.assert_called()


# ===========================================================================
# Graceful degradation
# ===========================================================================


class TestGracefulDegradation:
    """Tests for graceful behavior when Neo4j is unavailable."""

    async def test_get_entity_graph_returns_none_when_neo4j_down(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
    ) -> None:
        """get_entity_graph returns None when Neo4j is unreachable."""
        mock_neo4j.get_entity_graph = AsyncMock(side_effect=Neo4jConnectionError("refused"))

        result = await service.get_entity_graph()

        assert result is None

    async def test_get_entity_neighbors_returns_none_when_neo4j_down(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
    ) -> None:
        """get_entity_neighbors returns None when Neo4j is unreachable."""
        mock_neo4j.get_entity_neighbors = AsyncMock(side_effect=Neo4jConnectionError("refused"))

        result = await service.get_entity_neighbors("Josh")

        assert result is None

    async def test_add_to_graph_handles_neo4j_down(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
    ) -> None:
        """add_to_graph logs warning but doesn't crash when Neo4j is down."""
        mock_llm.generate_json = AsyncMock(
            side_effect=[
                {"entities": [{"entity": "Josh", "entity_type": "person"}]},
                {"relations": []},
                {"relations_to_delete": []},
            ]
        )
        mock_neo4j.merge_node = AsyncMock(side_effect=Neo4jConnectionError("refused"))

        # Should not raise
        await service.add_to_graph("Josh is here")

    async def test_search_graph_returns_empty_when_neo4j_down(
        self,
        service: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
    ) -> None:
        """search_graph returns empty list when Neo4j is unreachable."""
        mock_neo4j.query = AsyncMock(side_effect=Neo4jConnectionError("refused"))

        result = await service.search_graph("test")

        assert result == []

    async def test_add_to_graph_handles_llm_failure(
        self,
        service: KnowledgeGraphService,
        mock_llm: AsyncMock,
        mock_neo4j: AsyncMock,
    ) -> None:
        """add_to_graph handles LLM extraction failure gracefully."""
        mock_llm.generate_json = AsyncMock(side_effect=Exception("LLM error"))

        # Should not raise
        await service.add_to_graph("some content")

        mock_neo4j.merge_node.assert_not_called()


# ===========================================================================
# Cross-graph linking: RELATES_TO_CODE
# ===========================================================================


@pytest.fixture
def mock_vector_store() -> AsyncMock:
    """Mock VectorStore for code symbol searches."""
    store = AsyncMock()
    store.search = AsyncMock(return_value=[])
    return store


@pytest.fixture
def service_with_vector_store(
    mock_neo4j: AsyncMock,
    mock_llm: AsyncMock,
    mock_embed_fn: AsyncMock,
    mock_prompt_loader: MagicMock,
    mock_vector_store: AsyncMock,
) -> KnowledgeGraphService:
    """KnowledgeGraphService with VectorStore for code linking tests."""
    return KnowledgeGraphService(
        neo4j_client=mock_neo4j,
        llm_provider=mock_llm,
        embed_fn=mock_embed_fn,
        prompt_loader=mock_prompt_loader,
        vector_store=mock_vector_store,
        code_link_min_score=0.82,
        code_symbol_collection_prefix="code_symbols_",
    )


def _stub_llm_for_entities(mock_llm: AsyncMock, entities: list[dict[str, str]]) -> None:
    """Configure mock LLM to return the given entities with no relationships."""
    mock_llm.generate_json = AsyncMock(
        side_effect=[
            {"entities": entities},
            {"relations": []},
            {"relations_to_delete": []},
        ]
    )


class TestRelatesToCode:
    """Tests for RELATES_TO_CODE cross-graph linking (Step 9)."""

    async def test_writes_edges_for_hits_above_threshold(
        self,
        service_with_vector_store: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
        mock_vector_store: AsyncMock,
    ) -> None:
        """RELATES_TO_CODE edges are written when symbol matches exceed threshold."""
        _stub_llm_for_entities(mock_llm, [{"entity": "auth", "entity_type": "concept"}])
        mock_vector_store.search = AsyncMock(
            return_value=[("sym-uuid-1", 0.90), ("sym-uuid-2", 0.85)]
        )

        await service_with_vector_store.add_to_graph(
            "auth module", memory_id="mem-1", project_id="proj-1"
        )

        # Find the UNWIND RELATES_TO_CODE query call
        relates_calls = [c for c in mock_neo4j.query.call_args_list if "RELATES_TO_CODE" in str(c)]
        assert len(relates_calls) == 1
        call_args = relates_calls[0]
        links = (
            call_args.args[1]["links"]
            if len(call_args.args) > 1
            else call_args.kwargs.get("parameters", {}).get("links", [])
        )
        assert len(links) == 2
        assert links[0]["entity_name"] == "auth"
        assert links[0]["symbol_id"] == "sym-uuid-1"
        assert links[0]["score"] == 0.90

    async def test_filters_hits_below_threshold(
        self,
        service_with_vector_store: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
        mock_vector_store: AsyncMock,
    ) -> None:
        """Hits below code_link_min_score are not written as edges."""
        _stub_llm_for_entities(mock_llm, [{"entity": "auth", "entity_type": "concept"}])
        mock_vector_store.search = AsyncMock(
            return_value=[("sym-uuid-1", 0.75), ("sym-uuid-2", 0.60)]
        )

        await service_with_vector_store.add_to_graph(
            "auth module", memory_id="mem-1", project_id="proj-1"
        )

        relates_calls = [c for c in mock_neo4j.query.call_args_list if "RELATES_TO_CODE" in str(c)]
        assert len(relates_calls) == 0

    async def test_skips_when_no_project_id(
        self,
        service_with_vector_store: KnowledgeGraphService,
        mock_llm: AsyncMock,
        mock_vector_store: AsyncMock,
    ) -> None:
        """Step 9 is skipped entirely when project_id is None."""
        _stub_llm_for_entities(mock_llm, [{"entity": "auth", "entity_type": "concept"}])

        await service_with_vector_store.add_to_graph("auth module", memory_id="mem-1")

        mock_vector_store.search.assert_not_called()

    async def test_skips_when_no_vector_store(
        self,
        service: KnowledgeGraphService,
        mock_llm: AsyncMock,
        mock_neo4j: AsyncMock,
    ) -> None:
        """Step 9 is skipped when service has no VectorStore."""
        _stub_llm_for_entities(mock_llm, [{"entity": "auth", "entity_type": "concept"}])

        await service.add_to_graph("auth module", memory_id="mem-1", project_id="proj-1")

        relates_calls = [c for c in mock_neo4j.query.call_args_list if "RELATES_TO_CODE" in str(c)]
        assert len(relates_calls) == 0

    async def test_graceful_noop_when_collection_missing(
        self,
        service_with_vector_store: KnowledgeGraphService,
        mock_neo4j: AsyncMock,
        mock_llm: AsyncMock,
        mock_vector_store: AsyncMock,
    ) -> None:
        """Gracefully no-ops when Qdrant collection doesn't exist."""
        _stub_llm_for_entities(mock_llm, [{"entity": "auth", "entity_type": "concept"}])
        mock_vector_store.search = AsyncMock(
            side_effect=Exception("Collection code_symbols_proj-1 not found")
        )

        # Should not raise
        await service_with_vector_store.add_to_graph(
            "auth module", memory_id="mem-1", project_id="proj-1"
        )

        relates_calls = [c for c in mock_neo4j.query.call_args_list if "RELATES_TO_CODE" in str(c)]
        assert len(relates_calls) == 0

    async def test_uses_correct_collection_name(
        self,
        service_with_vector_store: KnowledgeGraphService,
        mock_llm: AsyncMock,
        mock_vector_store: AsyncMock,
    ) -> None:
        """Searches the correct Qdrant collection: prefix + project_id."""
        _stub_llm_for_entities(mock_llm, [{"entity": "auth", "entity_type": "concept"}])
        mock_vector_store.search = AsyncMock(return_value=[])

        await service_with_vector_store.add_to_graph(
            "auth module", memory_id="mem-1", project_id="my-project"
        )

        mock_vector_store.search.assert_called_once()
        call_kwargs = mock_vector_store.search.call_args.kwargs
        assert call_kwargs["collection_name"] == "code_symbols_my-project"
