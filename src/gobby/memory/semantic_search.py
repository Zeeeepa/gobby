"""
Semantic memory search using embeddings.

Provides embedding-based memory recall:
- Memory embedding storage and retrieval
- Cosine similarity search
- Integration with OpenAI text-embedding-3-small model

Reuses infrastructure from mcp_proxy.semantic_search.
"""

import hashlib
import logging
import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict

from gobby.storage.database import DatabaseProtocol
from gobby.storage.memories import Memory

logger = logging.getLogger(__name__)


class EmbedStats(TypedDict):
    """Statistics for embedding operations."""

    embedded: int
    skipped: int
    failed: int
    errors: list[str]


# Default embedding model (same as tool search)
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIM = 1536


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score between -1 and 1
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=True))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def _embedding_to_blob(embedding: list[float]) -> bytes:
    """Convert embedding list to binary BLOB."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def _embedding_from_blob(blob: bytes, dim: int) -> list[float]:
    """Convert binary BLOB to embedding list."""
    return list(struct.unpack(f"{dim}f", blob))


def _compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


@dataclass
class MemorySearchResult:
    """Represents a memory search result with similarity score."""

    memory: Memory
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = self.memory.to_dict()
        result["similarity"] = round(self.similarity, 4)
        return result


class SemanticMemorySearch:
    """
    Manages semantic search over memories using embeddings.

    Provides:
    - Embedding storage in memories.embedding BLOB column
    - Content hashing for change detection
    - Cosine similarity search
    - Integration with OpenAI embedding API via LiteLLM
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
        openai_api_key: str | None = None,
    ):
        """
        Initialize semantic memory search.

        Args:
            db: Database connection
            embedding_model: Model name for embeddings
            embedding_dim: Dimension of embedding vectors
            openai_api_key: OpenAI API key
        """
        self.db = db
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self._openai_api_key = openai_api_key

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for text using OpenAI via LiteLLM.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            RuntimeError: If API key not set or embedding fails
        """
        import os

        api_key = self._openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not configured. Add it to llm_providers.api_keys in config.yaml"
            )

        try:
            import litellm
        except ImportError as e:
            raise RuntimeError("litellm package not installed. Run: pip install litellm") from e

        try:
            response = await litellm.aembedding(
                model=self.embedding_model,
                input=[text],
                api_key=api_key,
            )
            embedding: list[float] = response.data[0]["embedding"]
            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def store_embedding(self, memory_id: str, embedding: list[float]) -> None:
        """
        Store embedding for a memory.

        Args:
            memory_id: Memory ID
            embedding: Embedding vector
        """
        now = datetime.now(UTC).isoformat()
        embedding_blob = _embedding_to_blob(embedding)

        self.db.execute(
            """
            UPDATE memories
            SET embedding = ?, updated_at = ?
            WHERE id = ?
            """,
            (embedding_blob, now, memory_id),
        )

    def get_embedding(self, memory_id: str) -> list[float] | None:
        """
        Get embedding for a memory.

        Args:
            memory_id: Memory ID

        Returns:
            Embedding vector or None if not found/not embedded
        """
        row = self.db.fetchone(
            "SELECT embedding FROM memories WHERE id = ?",
            (memory_id,),
        )
        if not row or not row["embedding"]:
            return None

        return _embedding_from_blob(row["embedding"], self.embedding_dim)

    def needs_embedding(self, memory_id: str) -> bool:
        """
        Check if a memory needs embedding.

        Args:
            memory_id: Memory ID

        Returns:
            True if embedding is missing
        """
        row = self.db.fetchone(
            "SELECT embedding FROM memories WHERE id = ?",
            (memory_id,),
        )
        return not row or not row["embedding"]

    async def embed_memory(
        self,
        memory_id: str,
        content: str,
        force: bool = False,
    ) -> bool:
        """
        Generate and store embedding for a memory.

        Args:
            memory_id: Memory ID
            content: Memory content to embed
            force: Force re-embedding even if exists

        Returns:
            True if embedding was generated, False if skipped
        """
        if not force and not self.needs_embedding(memory_id):
            logger.debug(f"Memory {memory_id} already has embedding, skipping")
            return False

        embedding = await self.embed_text(content)
        self.store_embedding(memory_id, embedding)
        logger.info(f"Embedded memory {memory_id}")
        return True

    async def embed_all_memories(
        self,
        project_id: str | None = None,
        force: bool = False,
    ) -> EmbedStats:
        """
        Generate embeddings for all memories.

        Args:
            project_id: Optional project filter
            force: Force re-embedding all

        Returns:
            Dict with statistics
        """
        stats: EmbedStats = {
            "embedded": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }

        # Get memories needing embedding
        if force:
            query = "SELECT id, content FROM memories"
            params: tuple[Any, ...] = ()
        else:
            query = "SELECT id, content FROM memories WHERE embedding IS NULL"
            params = ()

        if project_id:
            if "WHERE" in query:
                query += " AND (project_id = ? OR project_id IS NULL)"
            else:
                query += " WHERE (project_id = ? OR project_id IS NULL)"
            params = (project_id,)

        rows = self.db.fetchall(query, params)

        for row in rows:
            try:
                embedded = await self.embed_memory(
                    memory_id=row["id"],
                    content=row["content"],
                    force=force,
                )
                if embedded:
                    stats["embedded"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append(f"{row['id']}: {e}")
                logger.error(f"Failed to embed memory {row['id']}: {e}")

        return stats

    async def search(
        self,
        query: str,
        project_id: str | None = None,
        top_k: int = 10,
        min_similarity: float = 0.0,
        min_importance: float | None = None,
    ) -> list[MemorySearchResult]:
        """
        Search for memories semantically similar to a query.

        Args:
            query: Search query text
            project_id: Optional project filter
            top_k: Maximum results to return
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
            min_importance: Optional importance threshold

        Returns:
            List of MemorySearchResult sorted by similarity
        """
        # Embed the query
        query_embedding = await self.embed_text(query)

        # Get all memories with embeddings
        sql = """
            SELECT * FROM memories
            WHERE embedding IS NOT NULL
        """
        params: list[Any] = []

        if project_id:
            sql += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)

        if min_importance is not None:
            sql += " AND importance >= ?"
            params.append(min_importance)

        rows = self.db.fetchall(sql, tuple(params))

        if not rows:
            logger.debug("No memories with embeddings found")
            return []

        # Compute similarities
        results: list[MemorySearchResult] = []
        for row in rows:
            embedding = _embedding_from_blob(row["embedding"], self.embedding_dim)
            similarity = _cosine_similarity(query_embedding, embedding)

            if similarity >= min_similarity:
                memory = Memory.from_row(row)
                results.append(MemorySearchResult(memory=memory, similarity=similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    def get_embedding_stats(self, project_id: str | None = None) -> dict[str, Any]:
        """
        Get statistics about memory embeddings.

        Args:
            project_id: Optional project filter

        Returns:
            Dict with counts and model info
        """
        if project_id:
            total_row = self.db.fetchone(
                "SELECT COUNT(*) as count FROM memories WHERE project_id = ? OR project_id IS NULL",
                (project_id,),
            )
            embedded_row = self.db.fetchone(
                """
                SELECT COUNT(*) as count FROM memories
                WHERE embedding IS NOT NULL AND (project_id = ? OR project_id IS NULL)
                """,
                (project_id,),
            )
        else:
            total_row = self.db.fetchone("SELECT COUNT(*) as count FROM memories", ())
            embedded_row = self.db.fetchone(
                "SELECT COUNT(*) as count FROM memories WHERE embedding IS NOT NULL",
                (),
            )

        total = total_row["count"] if total_row else 0
        embedded = embedded_row["count"] if embedded_row else 0

        return {
            "total_memories": total,
            "embedded_memories": embedded,
            "pending_embeddings": total - embedded,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
        }

    def clear_embeddings(self, project_id: str | None = None) -> int:
        """
        Clear all embeddings (for rebuild).

        Args:
            project_id: Optional project filter

        Returns:
            Number of embeddings cleared
        """
        if project_id:
            cursor = self.db.execute(
                """
                UPDATE memories SET embedding = NULL
                WHERE project_id = ? OR project_id IS NULL
                """,
                (project_id,),
            )
        else:
            cursor = self.db.execute("UPDATE memories SET embedding = NULL", ())

        return cursor.rowcount
