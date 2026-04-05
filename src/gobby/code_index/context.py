"""Thin context object for code index daemon integration.

Holds storage, graph, and vector_store references for the daemon's
background tasks (maintenance, sync worker, HTTP routes). All actual
indexing is handled by gcode (Rust CLI).
"""

from __future__ import annotations

import logging
from typing import Any

from gobby.code_index.graph import CodeGraph
from gobby.code_index.storage import CodeIndexStorage
from gobby.config.code_index import CodeIndexConfig

logger = logging.getLogger(__name__)


class CodeIndexContext:
    """Daemon-side context for code index operations.

    Replaces the old CodeIndexer orchestrator — gcode now handles
    parsing, hashing, chunking, and writing to SQLite. This object
    provides access to storage/graph/vectors for the sync worker,
    maintenance loop, and HTTP invalidate endpoint.
    """

    def __init__(
        self,
        storage: CodeIndexStorage,
        vector_store: Any | None = None,
        graph: CodeGraph | None = None,
        config: CodeIndexConfig | None = None,
    ) -> None:
        self._storage = storage
        self._vector_store = vector_store
        self._graph = graph
        self._config = config or CodeIndexConfig()

    @property
    def storage(self) -> CodeIndexStorage:
        return self._storage

    @property
    def graph(self) -> CodeGraph | None:
        return self._graph

    @property
    def config(self) -> CodeIndexConfig:
        return self._config

    async def invalidate(self, project_id: str) -> None:
        """Clear all index data for a project."""
        self._storage.delete_symbols_for_project(project_id)
        self._storage.delete_files_for_project(project_id)
        self._storage.delete_content_chunks_for_project(project_id)

        if self._graph is not None:
            await self._graph.clear_project(project_id)

        if self._vector_store is not None:
            collection = f"{self._config.qdrant_collection_prefix}{project_id}"
            try:
                await self._vector_store.delete_collection(collection)
            except Exception as e:
                logger.debug(f"Vector collection delete failed: {e}")

        logger.info(f"Invalidated code index for project {project_id}")
