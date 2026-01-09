"""
Session artifacts storage module.

Stores code snippets, diffs, errors, and other artifacts from sessions
with optional FTS5 full-text search support.
"""

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import LocalDatabase
from gobby.utils.id import generate_prefixed_id

logger = logging.getLogger(__name__)


@dataclass
class Artifact:
    """A session artifact representing code, diff, error, or other content."""

    id: str
    session_id: str
    artifact_type: str
    content: str
    created_at: str
    metadata: dict[str, Any] | None = None
    source_file: str | None = None
    line_start: int | None = None
    line_end: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Artifact":
        """Create an Artifact from a database row."""
        metadata_json = row["metadata_json"]
        metadata = json.loads(metadata_json) if metadata_json else None

        return cls(
            id=row["id"],
            session_id=row["session_id"],
            artifact_type=row["artifact_type"],
            content=row["content"],
            created_at=row["created_at"],
            metadata=metadata,
            source_file=row["source_file"],
            line_start=row["line_start"],
            line_end=row["line_end"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert artifact to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "artifact_type": self.artifact_type,
            "content": self.content,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "source_file": self.source_file,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }


class LocalArtifactManager:
    """Manages session artifacts in local SQLite database."""

    def __init__(self, db: LocalDatabase):
        self.db = db
        self._change_listeners: list[Callable[[], Any]] = []

    def add_change_listener(self, listener: Callable[[], Any]) -> None:
        """Add a change listener that will be called on create/delete."""
        self._change_listeners.append(listener)

    def _notify_listeners(self) -> None:
        """Notify all change listeners."""
        for listener in self._change_listeners:
            try:
                listener()
            except Exception as e:
                logger.error(f"Error in artifact change listener: {e}")

    def create_artifact(
        self,
        session_id: str,
        artifact_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        source_file: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
    ) -> Artifact:
        """Create a new artifact.

        Args:
            session_id: ID of the session this artifact belongs to
            artifact_type: Type of artifact (code, diff, error, etc.)
            content: The artifact content
            metadata: Optional metadata dict
            source_file: Optional source file path
            line_start: Optional starting line number
            line_end: Optional ending line number

        Returns:
            The created Artifact
        """
        now = datetime.now(UTC).isoformat()
        artifact_id = generate_prefixed_id("art", content[:50] + session_id)

        metadata_json = json.dumps(metadata) if metadata else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO session_artifacts (
                    id, session_id, artifact_type, content, metadata_json,
                    source_file, line_start, line_end, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    session_id,
                    artifact_type,
                    content,
                    metadata_json,
                    source_file,
                    line_start,
                    line_end,
                    now,
                ),
            )

        self._notify_listeners()
        return self.get_artifact(artifact_id)  # type: ignore[return-value]

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        """Get an artifact by ID.

        Args:
            artifact_id: The artifact ID

        Returns:
            The Artifact if found, None otherwise
        """
        row = self.db.fetchone(
            "SELECT * FROM session_artifacts WHERE id = ?", (artifact_id,)
        )
        if not row:
            return None
        return Artifact.from_row(row)

    def list_artifacts(
        self,
        session_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Artifact]:
        """List artifacts with optional filters.

        Args:
            session_id: Filter by session ID
            artifact_type: Filter by artifact type
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of matching Artifacts
        """
        query = "SELECT * FROM session_artifacts WHERE 1=1"
        params: list[Any] = []

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        if artifact_type:
            query += " AND artifact_type = ?"
            params.append(artifact_type)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(query, tuple(params))
        return [Artifact.from_row(row) for row in rows]

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact by ID.

        Args:
            artifact_id: The artifact ID to delete

        Returns:
            True if deleted, False if not found
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM session_artifacts WHERE id = ?", (artifact_id,)
            )
            if cursor.rowcount == 0:
                return False

        self._notify_listeners()
        return True
