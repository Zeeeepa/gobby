"""Knowledge graph service for entity/relationship extraction and Neo4j storage.

Extracts entities and relationships from content using LLM prompts,
then merges them into a Neo4j knowledge graph.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gobby.memory.neo4j_client import Neo4jConnectionError

if TYPE_CHECKING:
    from collections.abc import Callable

    from gobby.llm.base import LLMProvider
    from gobby.memory.neo4j_client import Neo4jClient
    from gobby.prompts.loader import PromptLoader

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """An extracted entity from content."""

    name: str
    entity_type: str


@dataclass
class Relationship:
    """An extracted relationship between entities."""

    source: str
    target: str
    relationship: str


class KnowledgeGraphService:
    """Manages knowledge graph operations: entity/relationship extraction and Neo4j storage.

    Args:
        neo4j_client: Neo4j HTTP client for graph operations
        llm_provider: LLM provider for entity/relationship extraction
        embed_fn: Async function to generate embeddings for entity names
        prompt_loader: PromptLoader for rendering extraction prompts
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        llm_provider: LLMProvider,
        embed_fn: Callable[..., Any],
        prompt_loader: PromptLoader,
    ):
        self._neo4j = neo4j_client
        self._llm = llm_provider
        self._embed_fn = embed_fn
        self._prompt_loader = prompt_loader

    # -----------------------------------------------------------------------
    # Write path
    # -----------------------------------------------------------------------

    async def add_to_graph(self, content: str) -> None:
        """Extract entities and relationships from content and merge into Neo4j.

        Pipeline:
        1. Extract entities via LLM
        2. Extract relationships via LLM
        3. Fetch existing relationships for overlap detection
        4. Delete outdated relationships via LLM decision
        5. Merge nodes and relationships into Neo4j
        6. Set embedding vectors on nodes
        """
        # Step 1: Extract entities
        try:
            entities = await self._extract_entities(content)
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return

        if not entities:
            return

        # Step 2: Extract relationships
        try:
            relationships = await self._extract_relationships(content, entities)
        except Exception as e:
            logger.warning(f"Relationship extraction failed: {e}")
            relationships = []

        # Step 3-4: Handle outdated relationships
        try:
            await self._delete_outdated_relations(entities, relationships)
        except Exception as e:
            logger.warning(f"Relation cleanup failed: {e}")

        # Step 5: Merge nodes
        for entity in entities:
            try:
                await self._neo4j.merge_node(
                    name=entity.name,
                    labels=[entity.entity_type.capitalize()],
                    properties={"entity_type": entity.entity_type},
                )
            except Neo4jConnectionError as e:
                logger.warning(f"Neo4j unreachable during merge_node: {e}")
                return
            except Exception as e:
                logger.warning(f"Failed to merge node {entity.name}: {e}")

        # Merge relationships
        for rel in relationships:
            try:
                await self._neo4j.merge_relationship(
                    source=rel.source,
                    target=rel.target,
                    rel_type=rel.relationship,
                )
            except Neo4jConnectionError as e:
                logger.warning(f"Neo4j unreachable during merge_relationship: {e}")
                return
            except Exception as e:
                logger.warning(f"Failed to merge relationship {rel}: {e}")

        # Step 6: Set embeddings
        for entity in entities:
            try:
                embedding = await self._embed_fn(entity.name)
                await self._neo4j.set_node_vector(
                    node_name=entity.name,
                    embedding=embedding,
                )
            except Neo4jConnectionError as e:
                logger.warning(f"Neo4j unreachable during set_node_vector: {e}")
                return
            except Exception as e:
                logger.warning(f"Failed to set embedding for {entity.name}: {e}")

    async def _extract_entities(self, content: str) -> list[Entity]:
        """Extract entities from content using LLM."""
        prompt = self._prompt_loader.render(
            "memory/extract_entities",
            {"content": content},
        )
        response = await self._llm.generate_json(prompt)
        raw_entities = response.get("entities", [])
        return [
            Entity(name=e["entity"], entity_type=e["entity_type"])
            for e in raw_entities
            if isinstance(e, dict) and "entity" in e and "entity_type" in e
        ]

    async def _extract_relationships(
        self, content: str, entities: list[Entity]
    ) -> list[Relationship]:
        """Extract relationships between entities using LLM."""
        entities_json = json.dumps(
            [{"entity": e.name, "entity_type": e.entity_type} for e in entities]
        )
        prompt = self._prompt_loader.render(
            "memory/extract_relations",
            {"content": content, "entities": entities_json},
        )
        response = await self._llm.generate_json(prompt)
        raw_relations = response.get("relations", [])
        return [
            Relationship(
                source=r["source"],
                target=r["destination"],
                relationship=r["relationship"],
            )
            for r in raw_relations
            if isinstance(r, dict)
            and all(k in r for k in ("source", "relationship", "destination"))
        ]

    async def _delete_outdated_relations(
        self, entities: list[Entity], new_relations: list[Relationship]
    ) -> None:
        """Find and delete outdated relationships from Neo4j."""
        entity_names = [e.name for e in entities]
        if not entity_names:
            return

        # Fetch existing relationships for these entities
        try:
            existing = await self._fetch_existing_relations(entity_names)
        except Neo4jConnectionError:
            return

        if not existing:
            return

        new_relations_json = json.dumps(
            [
                {"source": r.source, "relationship": r.relationship, "destination": r.target}
                for r in new_relations
            ]
        )
        existing_json = json.dumps(existing)

        prompt = self._prompt_loader.render(
            "memory/delete_relations",
            {"existing_relations": existing_json, "new_relations": new_relations_json},
        )
        response = await self._llm.generate_json(prompt)
        to_delete = response.get("relations_to_delete", [])

        for rel in to_delete:
            if not isinstance(rel, dict):
                continue
            source = rel.get("source", "")
            relationship = rel.get("relationship", "")
            destination = rel.get("destination", "")
            if source and relationship and destination:
                try:
                    await self._neo4j.query(
                        "MATCH (a {name: $source})-[r]->(b {name: $target}) "
                        "WHERE type(r) = $rel_type DELETE r",
                        {"source": source, "target": destination, "rel_type": relationship},
                    )
                except Neo4jConnectionError as e:
                    logger.warning(f"Neo4j unreachable during relation delete: {e}")
                    return

    async def _fetch_existing_relations(self, entity_names: list[str]) -> list[dict[str, str]]:
        """Fetch existing relationships involving the given entities."""
        rows = await self._neo4j.query(
            "MATCH (a)-[r]->(b) "
            "WHERE a.name IN $names OR b.name IN $names "
            "RETURN a.name AS source, type(r) AS rel_type, b.name AS target",
            {"names": entity_names},
        )
        return [
            {"source": r["source"], "relationship": r["rel_type"], "destination": r["target"]}
            for r in rows
        ]

    # -----------------------------------------------------------------------
    # Read path
    # -----------------------------------------------------------------------

    async def get_entity_graph(self, limit: int = 500) -> dict[str, Any] | None:
        """Get the entity graph for visualization.

        Returns None if Neo4j is unreachable.
        """
        try:
            return await self._neo4j.get_entity_graph(limit=limit)
        except Neo4jConnectionError as e:
            logger.warning(f"Neo4j unreachable: {e}")
            return None
        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return None

    async def get_entity_neighbors(self, name: str) -> dict[str, Any] | None:
        """Get neighbors for a single entity.

        Returns None if Neo4j is unreachable.
        """
        try:
            return await self._neo4j.get_entity_neighbors(name)
        except Neo4jConnectionError as e:
            logger.warning(f"Neo4j unreachable: {e}")
            return None
        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return None

    async def search_graph(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search the knowledge graph for entities matching a query.

        Returns empty list if Neo4j is unreachable.
        """
        try:
            rows = await self._neo4j.query(
                "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($query) "
                "RETURN n.name AS name, labels(n) AS labels, properties(n) AS props "
                "LIMIT $limit",
                {"query": query, "limit": limit},
            )
            return rows
        except Neo4jConnectionError as e:
            logger.warning(f"Neo4j unreachable: {e}")
            return []
        except Exception as e:
            logger.warning(f"Graph search failed: {e}")
            return []
