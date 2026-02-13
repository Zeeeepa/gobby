"""Neo4j knowledge graph service for memory entity relationships.

Extracted from manager.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.memory.neo4j_client import Neo4jConnectionError as _Neo4jConnError

if TYPE_CHECKING:
    from gobby.memory.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class GraphService:
    """Handles Neo4j knowledge graph queries."""

    def __init__(
        self,
        get_neo4j_client: Callable[[], Neo4jClient | None],
    ):
        self._get_neo4j_client = get_neo4j_client

    @property
    def _neo4j_client(self) -> Neo4jClient | None:
        """Dynamically resolve the Neo4j client."""
        return self._get_neo4j_client()

    async def get_entity_graph(self, limit: int = 500) -> dict[str, Any] | None:
        """Get the Neo4j entity graph for visualization.

        Returns None if Neo4j is not configured or unreachable.
        """
        if not self._neo4j_client:
            return None
        try:
            return await self._neo4j_client.get_entity_graph(limit=limit)
        except _Neo4jConnError as e:
            logger.warning(f"Neo4j unreachable: {e}")
            return None
        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return None

    async def get_entity_neighbors(self, name: str) -> dict[str, Any] | None:
        """Get neighbors for a single Neo4j entity.

        Returns None if Neo4j is not configured or unreachable.
        """
        if not self._neo4j_client:
            return None
        try:
            return await self._neo4j_client.get_entity_neighbors(name)
        except _Neo4jConnError as e:
            logger.warning(f"Neo4j unreachable: {e}")
            return None
        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return None
