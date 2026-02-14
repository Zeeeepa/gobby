"""Tests for Neo4jClient write convenience methods."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from gobby.memory.neo4j_client import Neo4jClient

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def client() -> Neo4jClient:
    """Create a Neo4jClient with no real connection."""
    return Neo4jClient(url="http://localhost:7474", auth="neo4j:password")


class TestMergeNode:
    """Tests for merge_node()."""

    async def test_merge_node_basic(self, client: Neo4jClient) -> None:
        """merge_node generates MERGE with ON CREATE/ON MATCH SET."""
        client.query = AsyncMock(return_value=[])

        await client.merge_node("Alice", labels=["Person"], properties={"age": 30})

        client.query.assert_called_once()
        cypher = client.query.call_args[0][0]
        params = client.query.call_args[0][1]

        assert "MERGE" in cypher
        assert "ON CREATE SET" in cypher
        assert "ON MATCH SET" in cypher
        assert params["name"] == "Alice"
        assert params["props"]["age"] == 30

    async def test_merge_node_sets_labels(self, client: Neo4jClient) -> None:
        """merge_node applies labels to the node."""
        client.query = AsyncMock(return_value=[])

        await client.merge_node("Bob", labels=["Person", "Developer"])

        cypher = client.query.call_args[0][0]
        assert ":Person:Developer" in cypher

    async def test_merge_node_no_labels(self, client: Neo4jClient) -> None:
        """merge_node works without labels."""
        client.query = AsyncMock(return_value=[])

        await client.merge_node("Charlie")

        cypher = client.query.call_args[0][0]
        # Should still MERGE on name
        assert "MERGE" in cypher
        params = client.query.call_args[0][1]
        assert params["name"] == "Charlie"

    async def test_merge_node_empty_properties(self, client: Neo4jClient) -> None:
        """merge_node with no properties still sets name."""
        client.query = AsyncMock(return_value=[])

        await client.merge_node("Diana", labels=["Entity"])

        params = client.query.call_args[0][1]
        assert params["name"] == "Diana"


class TestMergeRelationship:
    """Tests for merge_relationship()."""

    async def test_merge_relationship_basic(self, client: Neo4jClient) -> None:
        """merge_relationship generates MATCH + MERGE for relationship."""
        client.query = AsyncMock(return_value=[])

        await client.merge_relationship("Alice", "Bob", "KNOWS", {"since": 2020})

        client.query.assert_called_once()
        cypher = client.query.call_args[0][0]
        params = client.query.call_args[0][1]

        assert "MATCH" in cypher
        assert "MERGE" in cypher
        assert "KNOWS" in cypher
        assert params["source_name"] == "Alice"
        assert params["target_name"] == "Bob"
        assert params["props"]["since"] == 2020

    async def test_merge_relationship_no_properties(self, client: Neo4jClient) -> None:
        """merge_relationship works without properties."""
        client.query = AsyncMock(return_value=[])

        await client.merge_relationship("Alice", "Bob", "FRIENDS")

        cypher = client.query.call_args[0][0]
        params = client.query.call_args[0][1]
        assert "FRIENDS" in cypher
        assert params["props"] == {}

    async def test_merge_relationship_sets_properties(self, client: Neo4jClient) -> None:
        """merge_relationship applies ON CREATE SET and ON MATCH SET."""
        client.query = AsyncMock(return_value=[])

        await client.merge_relationship("X", "Y", "RELATED", {"weight": 0.5})

        cypher = client.query.call_args[0][0]
        assert "ON CREATE SET" in cypher
        assert "ON MATCH SET" in cypher


class TestSetNodeVector:
    """Tests for set_node_vector()."""

    async def test_set_node_vector(self, client: Neo4jClient) -> None:
        """set_node_vector calls db.create.setNodeVectorProperty."""
        client.query = AsyncMock(return_value=[])
        embedding = [0.1, 0.2, 0.3]

        await client.set_node_vector("Alice", embedding)

        client.query.assert_called_once()
        cypher = client.query.call_args[0][0]
        params = client.query.call_args[0][1]

        assert "db.create.setNodeVectorProperty" in cypher
        assert params["name"] == "Alice"
        assert params["embedding"] == embedding

    async def test_set_node_vector_custom_property(self, client: Neo4jClient) -> None:
        """set_node_vector supports custom vector property name."""
        client.query = AsyncMock(return_value=[])

        await client.set_node_vector("Bob", [0.5], property_name="custom_vec")

        cypher = client.query.call_args[0][0]
        assert "custom_vec" in cypher

    async def test_set_node_vector_custom_index(self, client: Neo4jClient) -> None:
        """set_node_vector accepts custom index name parameter."""
        client.query = AsyncMock(return_value=[])

        # Should not raise — index_name is accepted as a parameter
        await client.set_node_vector("Carol", [0.5], index_name="my_index")

        client.query.assert_called_once()
