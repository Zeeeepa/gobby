"""Async Neo4j HTTP client.

Provides a direct HTTP client for the Neo4j HTTP Query API v2,
used to query the knowledge graph built by the KnowledgeGraphService.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class Neo4jConnectionError(Exception):
    """Raised when unable to connect to the Neo4j HTTP API."""


class Neo4jQueryError(Exception):
    """Raised when a Cypher query returns an error."""

    def __init__(self, message: str, status_code: int = 0, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


_CYPHER_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_cypher_identifier(value: str, kind: str = "identifier") -> None:
    """Validate that a value is a safe Cypher identifier.

    Raises ValueError if the value contains characters that could
    enable Cypher injection when interpolated into a query.
    """
    if not _CYPHER_IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid Cypher {kind}: {value!r}. Must match [A-Za-z_][A-Za-z0-9_]*.")


class Neo4jClient:
    """Async HTTP client for the Neo4j HTTP Query API v2.

    Args:
        url: Neo4j HTTP API base URL (e.g. http://localhost:7474)
        auth: Authentication string in 'user:password' format
        database: Neo4j database name (default: 'neo4j')
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        url: str,
        auth: str | None = None,
        database: str = "neo4j",
        timeout: float = 15.0,
    ):
        self._base_url = url.rstrip("/")
        self._database = database
        self._timeout = timeout

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if auth:
            encoded = base64.b64encode(auth.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def query(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query via the HTTP Query API v2.

        Args:
            cypher: Cypher query string
            params: Query parameters

        Returns:
            List of result rows as dicts
        """
        body: dict[str, Any] = {"statement": cypher}
        if params:
            body["parameters"] = params

        path = f"/db/{self._database}/query/v2"

        try:
            response = await self._client.post(path, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise Neo4jConnectionError(f"Neo4j connection refused: {e}") from e
        except httpx.TimeoutException as e:
            raise Neo4jConnectionError(f"Neo4j request timed out: {e}") from e

        if not response.is_success:
            try:
                resp_body = response.json()
            except Exception:
                resp_body = response.text
            raise Neo4jQueryError(
                f"Neo4j query error: HTTP {response.status_code}",
                status_code=response.status_code,
                response_body=resp_body,
            )

        data = response.json()
        return self._parse_response(data)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse Neo4j HTTP API v2 response into flat row dicts.

        The v2 API returns: {"data": {"fields": [...], "values": [[...], ...]}}
        """
        result_data = data.get("data", {})
        fields = result_data.get("fields", [])
        values = result_data.get("values", [])

        rows: list[dict[str, Any]] = []
        for row_values in values:
            row: dict[str, Any] = {}
            for i, field in enumerate(fields):
                val = row_values[i] if i < len(row_values) else None
                row[field] = val
            rows.append(row)
        return rows

    @staticmethod
    def _clean_props(props: Any) -> dict[str, Any]:
        """Strip large/unhelpful properties like embedding vectors."""
        if not isinstance(props, dict):
            return {}
        return {
            k: v
            for k, v in props.items()
            if not (isinstance(v, list) and len(v) > 20)  # skip embedding vectors
            and k not in ("embedding",)
        }

    async def get_entity_graph(self, limit: int = 500) -> dict[str, Any]:
        """Get entities and relationships for visualization.

        Returns:
            Dict with 'entities' and 'relationships' lists
        """
        # Fetch entities
        entity_rows = await self.query(
            "MATCH (n) RETURN n.name AS name, labels(n) AS labels, properties(n) AS props LIMIT $limit",
            {"limit": limit},
        )

        entities: list[dict[str, Any]] = []
        seen_entities: set[str] = set()
        for row in entity_rows:
            name = row.get("name") or ""
            if not name or name in seen_entities:
                continue
            seen_entities.add(name)
            labels = row.get("labels", [])
            props = row.get("props", {})
            # Use first non-generic label as type
            entity_type = "entity"
            if isinstance(labels, list):
                for label in labels:
                    if label not in ("Node", "_Entity"):
                        entity_type = label.lower()
                        break
            entities.append(
                {
                    "name": name,
                    "type": entity_type,
                    "properties": self._clean_props(props),
                }
            )

        # Fetch relationships
        rel_rows = await self.query(
            "MATCH (a)-[r]->(b) "
            "RETURN a.name AS source, b.name AS target, type(r) AS rel_type, properties(r) AS props "
            "LIMIT $limit",
            {"limit": limit * 4},
        )

        relationships: list[dict[str, Any]] = []
        for row in rel_rows:
            source = row.get("source") or ""
            target = row.get("target") or ""
            if not source or not target:
                continue
            if source not in seen_entities or target not in seen_entities:
                continue
            rel_type = row.get("rel_type", "RELATED")
            props = row.get("props", {})
            relationships.append(
                {
                    "source": source,
                    "target": target,
                    "type": rel_type,
                    "properties": self._clean_props(props),
                }
            )

        return {"entities": entities, "relationships": relationships}

    async def get_entity_neighbors(self, entity_name: str) -> dict[str, Any]:
        """Expand a single entity's connections.

        Args:
            entity_name: Name of the entity to expand

        Returns:
            Dict with 'entities' and 'relationships' for the neighborhood
        """
        rows = await self.query(
            "MATCH (a {name: $name})-[r]-(b) "
            "RETURN a.name AS source_name, labels(a) AS source_labels, properties(a) AS source_props, "
            "b.name AS target_name, labels(b) AS target_labels, properties(b) AS target_props, "
            "type(r) AS rel_type, properties(r) AS rel_props, "
            "startNode(r) = a AS is_outgoing "
            "LIMIT 50",
            {"name": entity_name},
        )

        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        seen: set[str] = set()

        for row in rows:
            # Add neighbor entity
            target_name = row.get("target_name") or ""
            if target_name and target_name not in seen:
                seen.add(target_name)
                labels = row.get("target_labels", [])
                entity_type = "entity"
                if isinstance(labels, list):
                    for label in labels:
                        if label not in ("Node", "_Entity"):
                            entity_type = label.lower()
                            break
                entities.append(
                    {
                        "name": target_name,
                        "type": entity_type,
                        "properties": self._clean_props(row.get("target_props", {})),
                    }
                )

            # Add relationship
            source_name = row.get("source_name") or ""
            rel_type = row.get("rel_type", "RELATED")
            is_outgoing = row.get("is_outgoing", True)

            if source_name and target_name:
                rel_props = self._clean_props(row.get("rel_props", {}))
                if is_outgoing:
                    relationships.append(
                        {
                            "source": source_name,
                            "target": target_name,
                            "type": rel_type,
                            "properties": rel_props,
                        }
                    )
                else:
                    relationships.append(
                        {
                            "source": target_name,
                            "target": source_name,
                            "type": rel_type,
                            "properties": rel_props,
                        }
                    )

        # Add the center entity itself if not already present
        if entity_name not in seen:
            # Fetch the center entity's labels
            center_rows = await self.query(
                "MATCH (n {name: $name}) RETURN labels(n) AS labels, properties(n) AS props LIMIT 1",
                {"name": entity_name},
            )
            entity_type = "entity"
            props: dict[str, Any] = {}
            if center_rows:
                labels = center_rows[0].get("labels", [])
                props = center_rows[0].get("props", {})
                if isinstance(labels, list):
                    for label in labels:
                        if label not in ("Node", "_Entity"):
                            entity_type = label.lower()
                            break
            entities.append(
                {
                    "name": entity_name,
                    "type": entity_type,
                    "properties": self._clean_props(props),
                }
            )

        return {"entities": entities, "relationships": relationships}

    async def merge_node(
        self,
        name: str,
        labels: list[str] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Merge a node by name, creating or updating it.

        Uses MERGE with ON CREATE SET / ON MATCH SET to upsert.

        Args:
            name: Node name (used as the merge key)
            labels: Neo4j labels to apply (e.g. ["Person", "Engineer"])
            properties: Additional properties to set on the node
        """
        props = dict(properties or {})
        if labels:
            for label in labels:
                _validate_cypher_identifier(label, "label")
        label_clause = ":" + ":".join(labels) if labels else ""
        cypher = (
            f"MERGE (n{label_clause} {{name: $name}}) "
            "ON CREATE SET n += $props "
            "ON MATCH SET n += $props "
            "RETURN n.name AS name"
        )
        return await self.query(cypher, {"name": name, "props": props})

    async def merge_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Merge a relationship between two nodes matched by name.

        Args:
            source: Source node name
            target: Target node name
            rel_type: Relationship type (e.g. "KNOWS")
            properties: Properties to set on the relationship
        """
        _validate_cypher_identifier(rel_type, "relationship type")
        props = dict(properties or {})
        cypher = (
            "MATCH (a {name: $source_name}), (b {name: $target_name}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "ON CREATE SET r += $props "
            "ON MATCH SET r += $props "
            "RETURN type(r) AS rel_type"
        )
        return await self.query(
            cypher, {"source_name": source, "target_name": target, "props": props}
        )

    async def set_node_vector(
        self,
        node_name: str,
        embedding: list[float],
        property_name: str = "embedding",
    ) -> list[dict[str, Any]]:
        """Set a vector property on a node using Neo4j's vector procedure.

        Args:
            node_name: Name of the node to set the vector on
            embedding: The embedding vector
            property_name: Vector property name (default: 'embedding')
        """
        _validate_cypher_identifier(property_name, "property name")
        cypher = (
            "MATCH (n {name: $name}) "
            f"CALL db.create.setNodeVectorProperty(n, '{property_name}', $embedding) "
            "RETURN n.name AS name"
        )
        return await self.query(cypher, {"name": node_name, "embedding": embedding})

    async def ping(self) -> bool:
        """Check if Neo4j is reachable."""
        try:
            await self.query("RETURN 1 AS ok")
            return True
        except (Neo4jConnectionError, Neo4jQueryError):
            return False
