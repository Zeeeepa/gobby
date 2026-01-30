"""
Component for handling Memory Manager's search and cross-referencing logic.
"""

from __future__ import annotations

import logging
from typing import Any

from gobby.config.persistence import MemoryConfig
from gobby.memory.search.coordinator import SearchCoordinator
from gobby.memory.services.crossref import CrossrefService
from gobby.storage.database import DatabaseProtocol
from gobby.storage.memories import LocalMemoryManager, Memory

logger = logging.getLogger(__name__)


class SearchService:
    """Service for handling memory search and cross-referencing."""

    def __init__(
        self,
        storage: LocalMemoryManager,
        config: MemoryConfig,
        db: DatabaseProtocol,
    ):
        self.storage = storage
        self.config = config

        self._search_coordinator = SearchCoordinator(
            storage=storage,
            config=config,
            db=db,
        )

        self._crossref_service = CrossrefService(
            storage=storage,
            config=config,
            search_backend_getter=lambda: self._search_coordinator.search_backend,
            ensure_fitted=self._search_coordinator.ensure_fitted,
        )

    @property
    def backend(self) -> Any:
        """Get the underlying search backend."""
        return self._search_coordinator.search_backend

    def ensure_fitted(self) -> None:
        """Ensure the search backend is fitted with current memories."""
        self._search_coordinator.ensure_fitted()

    def mark_refit_needed(self) -> None:
        """Mark that the search backend needs to be refitted."""
        self._search_coordinator.mark_refit_needed()

    def reindex(self) -> dict[str, Any]:
        """Force rebuild of the search index."""
        return self._search_coordinator.reindex()

    def search(
        self,
        query: str,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        search_mode: str | None = None,
        tags_all: list[str] | None = None,
        tags_any: list[str] | None = None,
        tags_none: list[str] | None = None,
    ) -> list[Memory]:
        """Perform search using the configured search backend."""
        return self._search_coordinator.search(
            query=query,
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
            search_mode=search_mode,
            tags_all=tags_all,
            tags_any=tags_any,
            tags_none=tags_none,
        )

    async def create_crossrefs(
        self,
        memory: Memory,
        threshold: float | None = None,
        max_links: int | None = None,
    ) -> int:
        """Find and link similar memories."""
        return await self._crossref_service.create_crossrefs(
            memory=memory,
            threshold=threshold,
            max_links=max_links,
        )

    async def get_related(
        self,
        memory_id: str,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[Memory]:
        """Get memories linked to this one via cross-references."""
        return await self._crossref_service.get_related(
            memory_id=memory_id,
            limit=limit,
            min_similarity=min_similarity,
        )
