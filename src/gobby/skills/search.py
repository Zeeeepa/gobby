"""Skill search with TF-IDF backend and optional hybrid mode.

This module provides skill search functionality using TF-IDF vectorization
for relevance ranking. It indexes skills by combining:
- name
- description
- tags (from metadata.skillport.tags)
- category (from metadata.skillport.category)

The search returns results ranked by cosine similarity to the query.

Hybrid mode (optional):
- Combines TF-IDF (40%) and embedding (60%) similarity scores
- Requires an EmbeddingProvider for generating embeddings
- Falls back to TF-IDF only if embeddings are unavailable
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from gobby.skills.embeddings import EmbeddingProvider
    from gobby.storage.skills import Skill

logger = logging.getLogger(__name__)

# Search modes
SearchMode = Literal["tfidf", "hybrid"]

# Default weights for hybrid search
DEFAULT_TFIDF_WEIGHT = 0.4
DEFAULT_EMBEDDING_WEIGHT = 0.6


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


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=True))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


class SkillSearch:
    """Search skills using TF-IDF similarity with optional hybrid mode.

    This class wraps TFIDFSearcher to provide skill-specific search
    functionality. It builds search content from multiple skill fields
    and maintains a mapping from skill IDs to names.

    Supports two modes:
    - "tfidf" (default): Uses TF-IDF similarity only
    - "hybrid": Combines TF-IDF (40%) and embedding (60%) similarity

    Example usage:
        ```python
        from gobby.skills.search import SkillSearch
        from gobby.storage.skills import LocalSkillManager

        # Basic TF-IDF search
        search = SkillSearch()
        skills = skill_manager.list_skills()
        search.index_skills(skills)
        results = search.search("git commit", top_k=5)

        # Hybrid search with embeddings
        from gobby.skills.embeddings import get_embedding_provider
        provider = get_embedding_provider()
        search = SkillSearch(mode="hybrid", embedding_provider=provider)
        await search.index_skills_async(skills)
        results = await search.search_async("git commit", top_k=5)
        ```
    """

    def __init__(
        self,
        ngram_range: tuple[int, int] = (1, 2),
        max_features: int = 5000,
        min_df: int = 1,
        refit_threshold: int = 10,
        mode: SearchMode = "tfidf",
        embedding_provider: EmbeddingProvider | None = None,
        tfidf_weight: float = DEFAULT_TFIDF_WEIGHT,
        embedding_weight: float = DEFAULT_EMBEDDING_WEIGHT,
    ):
        """Initialize skill search.

        Args:
            ngram_range: Min/max n-gram sizes for tokenization
            max_features: Maximum vocabulary size
            min_df: Minimum document frequency for inclusion
            refit_threshold: Number of updates before automatic refit
            mode: Search mode - "tfidf" or "hybrid"
            embedding_provider: Provider for generating embeddings (required for hybrid)
            tfidf_weight: Weight for TF-IDF score in hybrid mode (default: 0.4)
            embedding_weight: Weight for embedding score in hybrid mode (default: 0.6)
        """
        self._ngram_range = ngram_range
        self._max_features = max_features
        self._min_df = min_df
        self._refit_threshold = refit_threshold

        # Hybrid mode settings
        self._mode: SearchMode = mode
        self._embedding_provider = embedding_provider

        # Validate weights are non-negative
        if tfidf_weight < 0 or embedding_weight < 0:
            raise ValueError(
                f"Weights must be non-negative: tfidf_weight={tfidf_weight}, "
                f"embedding_weight={embedding_weight}"
            )

        # Normalize weights to sum to 1
        total_weight = tfidf_weight + embedding_weight
        if total_weight > 0:
            self._tfidf_weight = tfidf_weight / total_weight
            self._embedding_weight = embedding_weight / total_weight
        else:
            self._tfidf_weight = DEFAULT_TFIDF_WEIGHT
            self._embedding_weight = DEFAULT_EMBEDDING_WEIGHT

        # Internal state
        self._searcher: Any = None  # TFIDFSearcher, lazy loaded
        self._skill_names: dict[str, str] = {}  # skill_id -> skill_name
        self._skill_meta: dict[str, _SkillMeta] = {}  # skill_id -> metadata for filtering
        self._skill_embeddings: dict[str, list[float]] = {}  # skill_id -> embedding
        self._skill_content: dict[str, str] = {}  # skill_id -> search content (for embedding)
        self._indexed = False
        self._embeddings_indexed = False
        self._pending_updates = 0

    @property
    def mode(self) -> SearchMode:
        """Return the current search mode."""
        return self._mode

    @mode.setter
    def mode(self, value: SearchMode) -> None:
        """Set the search mode."""
        self._mode = value

    @property
    def tfidf_weight(self) -> float:
        """Return the TF-IDF weight for hybrid search."""
        return self._tfidf_weight

    @property
    def embedding_weight(self) -> float:
        """Return the embedding weight for hybrid search."""
        return self._embedding_weight

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

    async def index_skills_async(self, skills: list[Skill]) -> None:
        """Build search index from skills with embeddings for hybrid mode.

        This method indexes skills for both TF-IDF and embedding-based search.
        If no embedding provider is available, only TF-IDF is indexed.

        Args:
            skills: List of skills to index
        """
        # Always do TF-IDF indexing first
        self.index_skills(skills)

        # Generate embeddings if provider is available and mode is hybrid
        if self._mode == "hybrid" and self._embedding_provider is not None:
            try:
                # Build content for embedding
                texts = []
                skill_ids = []
                for skill in skills:
                    content = self._build_search_content(skill)
                    texts.append(content)
                    skill_ids.append(skill.id)
                    self._skill_content[skill.id] = content

                # Generate embeddings in batch
                embeddings = await self._embedding_provider.embed_batch(texts)

                # Store embeddings
                for skill_id, embedding in zip(skill_ids, embeddings, strict=True):
                    self._skill_embeddings[skill_id] = embedding

                self._embeddings_indexed = True
                logger.info(f"Generated embeddings for {len(skills)} skills")
            except Exception as e:
                logger.warning(f"Failed to generate embeddings, falling back to TF-IDF: {e}")
                self._embeddings_indexed = False

    async def search_async(
        self,
        query: str,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[SkillSearchResult]:
        """Search for skills using hybrid mode (TF-IDF + embeddings).

        Falls back to TF-IDF only if embeddings are unavailable.

        Args:
            query: Search query text
            top_k: Maximum number of results to return
            filters: Optional filters to apply after ranking

        Returns:
            List of SkillSearchResult objects, sorted by similarity descending
        """
        # If not in hybrid mode or no embeddings, use regular search
        if self._mode != "hybrid" or not self._embeddings_indexed:
            return self.search(query, top_k, filters)

        if not self._indexed or self._searcher is None:
            return []

        try:
            # Get TF-IDF scores
            search_limit = top_k * 3 if filters else top_k * 2
            tfidf_results = self._searcher.search(query, top_k=search_limit)
            tfidf_scores = {skill_id: score for skill_id, score in tfidf_results}

            # Get embedding similarity scores (with null check)
            embedding_scores: dict[str, float] = {}
            if self._embedding_provider is None:
                logger.warning(
                    "Embedding provider is None in hybrid search, using TF-IDF scores only"
                )
            else:
                query_embedding = await self._embedding_provider.embed(query)
                for skill_id, skill_embedding in self._skill_embeddings.items():
                    similarity = _cosine_similarity(query_embedding, skill_embedding)
                    embedding_scores[skill_id] = similarity

            # Combine scores with weights
            all_skill_ids = set(tfidf_scores.keys()) | set(embedding_scores.keys())
            combined_scores = {}
            for skill_id in all_skill_ids:
                tfidf_score = tfidf_scores.get(skill_id, 0.0)
                emb_score = embedding_scores.get(skill_id, 0.0)
                combined = (self._tfidf_weight * tfidf_score) + (self._embedding_weight * emb_score)
                combined_scores[skill_id] = combined

            # Sort by combined score
            sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)

            # Build results with filtering
            results = []
            for skill_id, similarity in sorted_results:
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

                if len(results) >= top_k:
                    break

            return results
        except Exception as e:
            logger.warning(f"Hybrid search failed, falling back to TF-IDF: {e}")
            return self.search(query, top_k, filters)

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
        self._skill_meta.pop(skill_id, None)
        self._skill_embeddings.pop(skill_id, None)

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
        self._skill_embeddings.clear()
        self._skill_content.clear()
        self._indexed = False
        self._embeddings_indexed = False
        self._pending_updates = 0
