"""Skill search with TF-IDF backend.

This module provides skill search functionality using TF-IDF vectorization
for relevance ranking. It indexes skills by combining:
- name
- description
- tags (from metadata.skillport.tags)
- category (from metadata.skillport.category)

The search returns results ranked by cosine similarity to the query.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.skills import Skill

logger = logging.getLogger(__name__)


@dataclass
class SearchFilters:
    """Filters to apply to search results.

    Filters are applied AFTER similarity ranking, so results maintain
    their relevance ordering within the filtered set.

    Attributes:
        category: Filter by skill category (exact match)
        tags_any: Filter to skills with ANY of these tags
        tags_all: Filter to skills with ALL of these tags
    """

    category: str | None = None
    tags_any: list[str] | None = None
    tags_all: list[str] | None = None


@dataclass
class SkillSearchResult:
    """A search result containing a skill ID and relevance score.

    Attributes:
        skill_id: ID of the matching skill
        skill_name: Name of the matching skill (for display)
        similarity: Relevance score in range [0, 1]
    """

    skill_id: str
    skill_name: str
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "similarity": self.similarity,
        }


@dataclass
class _SkillMeta:
    """Internal metadata about a skill for filtering."""

    name: str
    category: str | None
    tags: list[str]


class SkillSearch:
    """Search skills using TF-IDF similarity.

    This class wraps TFIDFSearcher to provide skill-specific search
    functionality. It builds search content from multiple skill fields
    and maintains a mapping from skill IDs to names.

    Example usage:
        ```python
        from gobby.skills.search import SkillSearch
        from gobby.storage.skills import LocalSkillManager

        search = SkillSearch()
        skills = skill_manager.list_skills()
        search.index_skills(skills)

        results = search.search("git commit", top_k=5)
        for result in results:
            print(f"{result.skill_name}: {result.similarity:.2f}")
        ```
    """

    def __init__(
        self,
        ngram_range: tuple[int, int] = (1, 2),
        max_features: int = 5000,
        min_df: int = 1,
        refit_threshold: int = 10,
    ):
        """Initialize skill search.

        Args:
            ngram_range: Min/max n-gram sizes for tokenization
            max_features: Maximum vocabulary size
            min_df: Minimum document frequency for inclusion
            refit_threshold: Number of updates before automatic refit
        """
        self._ngram_range = ngram_range
        self._max_features = max_features
        self._min_df = min_df
        self._refit_threshold = refit_threshold

        # Internal state
        self._searcher: Any = None  # TFIDFSearcher, lazy loaded
        self._skill_names: dict[str, str] = {}  # skill_id -> skill_name
        self._skill_meta: dict[str, _SkillMeta] = {}  # skill_id -> metadata for filtering
        self._indexed = False
        self._pending_updates = 0

    def _ensure_searcher(self) -> Any:
        """Create or return the TF-IDF searcher."""
        if self._searcher is None:
            from gobby.search.tfidf import TFIDFSearcher

            self._searcher = TFIDFSearcher(
                ngram_range=self._ngram_range,
                max_features=self._max_features,
                min_df=self._min_df,
                refit_threshold=self._refit_threshold,
            )
        return self._searcher

    def _build_search_content(self, skill: Skill) -> str:
        """Build searchable content from skill fields.

        Combines name, description, tags, and category into a single
        string for indexing.

        Args:
            skill: Skill to extract content from

        Returns:
            Combined search content string
        """
        parts = [
            skill.name,
            skill.description,
        ]

        # Add tags from metadata
        tags = skill.get_tags()
        if tags:
            parts.extend(tags)

        # Add category from metadata
        category = skill.get_category()
        if category:
            parts.append(category)

        return " ".join(parts)

    def index_skills(self, skills: list[Skill]) -> None:
        """Build search index from skills.

        Args:
            skills: List of skills to index
        """
        if not skills:
            self._skill_names.clear()
            self._skill_meta.clear()
            self._indexed = False
            self._pending_updates = 0
            logger.debug("Skill search index cleared (no skills)")
            return

        searcher = self._ensure_searcher()

        # Build (skill_id, content) tuples and metadata
        items: list[tuple[str, str]] = []
        self._skill_names.clear()
        self._skill_meta.clear()

        for skill in skills:
            content = self._build_search_content(skill)
            items.append((skill.id, content))
            self._skill_names[skill.id] = skill.name
            self._skill_meta[skill.id] = _SkillMeta(
                name=skill.name,
                category=skill.get_category(),
                tags=skill.get_tags(),
            )

        searcher.fit(items)
        self._indexed = True
        self._pending_updates = 0
        logger.info(f"Skill search index built with {len(skills)} skills")

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[SkillSearchResult]:
        """Search for skills matching the query.

        Args:
            query: Search query text
            top_k: Maximum number of results to return
            filters: Optional filters to apply after ranking

        Returns:
            List of SkillSearchResult objects, sorted by similarity descending
        """
        if not self._indexed or self._searcher is None:
            return []

        # Get more results than top_k if filtering, since filters reduce the set
        search_limit = top_k * 3 if filters else top_k
        raw_results = self._searcher.search(query, top_k=search_limit)

        results = []
        for skill_id, similarity in raw_results:
            # Apply filters if provided
            if filters and not self._passes_filters(skill_id, filters):
                continue

            skill_name = self._skill_names.get(skill_id, skill_id)
            results.append(
                SkillSearchResult(
                    skill_id=skill_id,
                    skill_name=skill_name,
                    similarity=similarity,
                )
            )

            # Stop once we have enough results
            if len(results) >= top_k:
                break

        return results

    def _passes_filters(self, skill_id: str, filters: SearchFilters) -> bool:
        """Check if a skill passes the given filters.

        Args:
            skill_id: ID of the skill to check
            filters: Filters to apply

        Returns:
            True if skill passes all filters
        """
        meta = self._skill_meta.get(skill_id)
        if not meta:
            return False

        # Check category filter
        if filters.category is not None:
            if meta.category != filters.category:
                return False

        # Check tags_any filter (skill must have at least one of the tags)
        if filters.tags_any is not None:
            if not any(tag in meta.tags for tag in filters.tags_any):
                return False

        # Check tags_all filter (skill must have all of the tags)
        if filters.tags_all is not None:
            if not all(tag in meta.tags for tag in filters.tags_all):
                return False

        return True

    def add_skill(self, skill: Skill) -> None:
        """Mark that a skill was added (requires reindex).

        This tracks the update but doesn't immediately reindex.
        Call index_skills() when needs_reindex() returns True.

        Args:
            skill: The skill that was added
        """
        self._pending_updates += 1
        self._skill_names[skill.id] = skill.name

    def update_skill(self, skill: Skill) -> None:
        """Mark that a skill was updated (requires reindex).

        Args:
            skill: The skill that was updated
        """
        self._pending_updates += 1
        self._skill_names[skill.id] = skill.name

    def remove_skill(self, skill_id: str) -> None:
        """Mark that a skill was removed (requires reindex).

        Args:
            skill_id: ID of the skill that was removed
        """
        self._pending_updates += 1
        self._skill_names.pop(skill_id, None)

    def needs_reindex(self) -> bool:
        """Check if the search index needs rebuilding.

        Returns:
            True if index_skills() should be called
        """
        if not self._indexed:
            return True
        return self._pending_updates >= self._refit_threshold

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the search index.

        Returns:
            Dict with index statistics
        """
        stats: dict[str, Any] = {
            "indexed": self._indexed,
            "skill_count": len(self._skill_names),
            "pending_updates": self._pending_updates,
            "refit_threshold": self._refit_threshold,
        }

        if self._searcher is not None:
            searcher_stats = self._searcher.get_stats()
            stats["vocabulary_size"] = searcher_stats.get("vocabulary_size")
            stats["ngram_range"] = self._ngram_range
            stats["max_features"] = self._max_features

        return stats

    def clear(self) -> None:
        """Clear the search index."""
        if self._searcher is not None:
            self._searcher.clear()
        self._skill_names.clear()
        self._skill_meta.clear()
        self._indexed = False
        self._pending_updates = 0
