"""Memory embedding persistence layer.

Stores and retrieves embedding vectors for memories, enabling
semantic search in the memory system. Follows the tool_embeddings
pattern from mcp_proxy/semantic_search.py.
"""

import logging
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


def _embedding_to_blob(embedding: list[float]) -> bytes:
    """Convert embedding list to binary BLOB."""
    return struct.pack(f"{len(embedding)}f", *embedding)


@dataclass
class MemoryEmbedding:
    """Represents a memory's embedding vector with metadata."""

    id: int
    memory_id: str
    project_id: str | None
    embedding: list[float]
    embedding_model: str
    embedding_dim: int
    text_hash: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Any) -> "MemoryEmbedding":
        """Create MemoryEmbedding from database row."""
        embedding_blob = row["embedding"]
        embedding = list(struct.unpack(f"{row['embedding_dim']}f", embedding_blob))

        return cls(
            id=row["id"],
            memory_id=row["memory_id"],
            project_id=row["project_id"],
            embedding=embedding,
            embedding_model=row["embedding_model"],
            embedding_dim=row["embedding_dim"],
            text_hash=row["text_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excludes embedding for serialization)."""
        return {
            "id": self.id,
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "text_hash": self.text_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MemoryEmbeddingManager:
    """Manages CRUD operations for memory embeddings."""

    def __init__(self, db: DatabaseProtocol) -> None:
        self.db = db

    def store_embedding(
        self,
        memory_id: str,
        project_id: str | None,
        embedding: list[float],
        embedding_model: str,
        text_hash: str,
    ) -> MemoryEmbedding:
        """Store or update a memory embedding (upsert on memory_id)."""
        now = datetime.now(UTC).isoformat()
        embedding_blob = _embedding_to_blob(embedding)

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memory_embeddings (
                    memory_id, project_id, embedding,
                    embedding_model, embedding_dim, text_hash, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    embedding = excluded.embedding,
                    embedding_model = excluded.embedding_model,
                    embedding_dim = excluded.embedding_dim,
                    text_hash = excluded.text_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    memory_id,
                    project_id,
                    embedding_blob,
                    embedding_model,
                    len(embedding),
                    text_hash,
                    now,
                    now,
                ),
            )

        result = self.get_embedding(memory_id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve embedding for memory {memory_id} after store")
        return result

    def get_embedding(self, memory_id: str) -> MemoryEmbedding | None:
        """Get embedding for a memory, or None if not found."""
        row = self.db.fetchone(
            "SELECT * FROM memory_embeddings WHERE memory_id = ?",
            (memory_id,),
        )
        return MemoryEmbedding.from_row(row) if row else None

    def delete_embedding(self, memory_id: str) -> bool:
        """Delete embedding for a memory. Returns True if deleted."""
        cursor = self.db.execute(
            "DELETE FROM memory_embeddings WHERE memory_id = ?",
            (memory_id,),
        )
        return cursor.rowcount > 0

    def get_embeddings_by_project(self, project_id: str) -> list[MemoryEmbedding]:
        """Get all embeddings for a project."""
        rows = self.db.fetchall(
            "SELECT * FROM memory_embeddings WHERE project_id = ?",
            (project_id,),
        )
        return [MemoryEmbedding.from_row(row) for row in rows]

    def get_all_embeddings(self) -> list[MemoryEmbedding]:
        """Get all stored memory embeddings."""
        rows = self.db.fetchall("SELECT * FROM memory_embeddings", ())
        return [MemoryEmbedding.from_row(row) for row in rows]

    def get_embeddings_needing_update(
        self, current_hashes: dict[str, str]
    ) -> list[MemoryEmbedding]:
        """Find embeddings whose text_hash doesn't match the current content hash.

        Args:
            current_hashes: Mapping of memory_id -> current text_hash

        Returns:
            List of MemoryEmbedding instances that are stale
        """
        if not current_hashes:
            return []

        all_embeddings = self.get_all_embeddings()
        return [
            e
            for e in all_embeddings
            if e.memory_id in current_hashes and e.text_hash != current_hashes[e.memory_id]
        ]

    def batch_store_embeddings(self, items: list[dict[str, Any]]) -> int:
        """Store multiple embeddings in a single transaction.

        Args:
            items: List of dicts with keys: memory_id, project_id, embedding,
                   embedding_model, text_hash

        Returns:
            Number of embeddings stored
        """
        now = datetime.now(UTC).isoformat()
        count = 0

        with self.db.transaction() as conn:
            for item in items:
                embedding = item["embedding"]
                embedding_blob = _embedding_to_blob(embedding)
                conn.execute(
                    """
                    INSERT INTO memory_embeddings (
                        memory_id, project_id, embedding,
                        embedding_model, embedding_dim, text_hash, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(memory_id) DO UPDATE SET
                        project_id = excluded.project_id,
                        embedding = excluded.embedding,
                        embedding_model = excluded.embedding_model,
                        embedding_dim = excluded.embedding_dim,
                        text_hash = excluded.text_hash,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item["memory_id"],
                        item.get("project_id"),
                        embedding_blob,
                        item["embedding_model"],
                        len(embedding),
                        item["text_hash"],
                        now,
                        now,
                    ),
                )
                count += 1

        return count
