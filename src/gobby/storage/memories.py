import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from gobby.storage.database import LocalDatabase
from gobby.utils.id import generate_prefixed_id

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    id: str
    memory_type: Literal["fact", "preference", "pattern", "context"]
    content: str
    created_at: str
    updated_at: str
    project_id: str | None = None
    source_type: Literal["user", "session", "inferred"] | None = None
    source_session_id: str | None = None
    importance: float = 0.5
    access_count: int = 0
    last_accessed_at: str | None = None
    tags: list[str] | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Memory":
        tags_json = row["tags"]
        tags = json.loads(tags_json) if tags_json else []

        return cls(
            id=row["id"],
            memory_type=row["memory_type"],
            content=row["content"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            project_id=row["project_id"],
            source_type=row["source_type"],
            source_session_id=row["source_session_id"],
            importance=row["importance"],
            access_count=row["access_count"],
            last_accessed_at=row["last_accessed_at"],
            tags=tags,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project_id": self.project_id,
            "source_type": self.source_type,
            "source_session_id": self.source_session_id,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at,
            "tags": self.tags,
        }


class LocalMemoryManager:
    def __init__(self, db: LocalDatabase):
        self.db = db
        self._change_listeners: list[Callable[[], Any]] = []

    def add_change_listener(self, listener: Callable[[], Any]) -> None:
        self._change_listeners.append(listener)

    def _notify_listeners(self) -> None:
        for listener in self._change_listeners:
            try:
                listener()
            except Exception as e:
                logger.error(f"Error in memory change listener: {e}")

    def create_memory(
        self,
        content: str,
        memory_type: str = "fact",
        project_id: str | None = None,
        source_type: str = "user",
        source_session_id: str | None = None,
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> Memory:
        now = datetime.now(UTC).isoformat()
        # Ensure consistent ID for same content/project to avoid dupes?
        # Actually random/content-based might be better. Let's use content.
        memory_id = generate_prefixed_id("mm", content + str(project_id))

        # Check if memory already exists to avoid duplicate insert errors
        existing_row = self.db.fetchone("SELECT * FROM memories WHERE id = ?", (memory_id,))
        if existing_row:
            return self.get_memory(memory_id)

        tags_json = json.dumps(tags) if tags else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, project_id, memory_type, content, source_type,
                    source_session_id, importance, access_count, tags,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    memory_id,
                    project_id,
                    memory_type,
                    content,
                    source_type,
                    source_session_id,
                    importance,
                    tags_json,
                    now,
                    now,
                ),
            )

        self._notify_listeners()
        return self.get_memory(memory_id)

    def get_memory(self, memory_id: str) -> Memory:
        row = self.db.fetchone("SELECT * FROM memories WHERE id = ?", (memory_id,))
        if not row:
            raise ValueError(f"Memory {memory_id} not found")
        return Memory.from_row(row)

    def memory_exists(self, memory_id: str) -> bool:
        """Check if a memory with the given ID exists."""
        row = self.db.fetchone("SELECT 1 FROM memories WHERE id = ?", (memory_id,))
        return row is not None

    def content_exists(self, content: str, project_id: str | None = None) -> bool:
        """Check if a memory with identical content already exists."""
        if project_id:
            row = self.db.fetchone(
                "SELECT 1 FROM memories WHERE content = ? AND project_id = ?",
                (content, project_id),
            )
        else:
            row = self.db.fetchone(
                "SELECT 1 FROM memories WHERE content = ? AND project_id IS NULL",
                (content,),
            )
        return row is not None

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        updates = []
        params: list[Any] = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))

        if not updates:
            return self.get_memory(memory_id)

        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(memory_id)

        # nosec B608: SET clause built from hardcoded column names, values parameterized
        sql = f"UPDATE memories SET {', '.join(updates)} WHERE id = ?"  # nosec B608

        with self.db.transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            if cursor.rowcount == 0:
                raise ValueError(f"Memory {memory_id} not found")

        self._notify_listeners()
        return self.get_memory(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            if cursor.rowcount == 0:
                return False
        self._notify_listeners()
        return True

    def list_memories(
        self,
        project_id: str | None = None,
        memory_type: str | None = None,
        min_importance: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[Any] = []

        if project_id:
            query += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)

        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)

        if min_importance is not None:
            query += " AND importance >= ?"
            params.append(min_importance)

        query += " ORDER BY importance DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(query, tuple(params))
        return [Memory.from_row(row) for row in rows]

    def update_access_stats(self, memory_id: str, accessed_at: str) -> None:
        """
        Update access count and last accessed timestamp for a memory.

        Args:
            memory_id: Memory ID to update
            accessed_at: ISO format timestamp of access
        """
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE memories
                SET access_count = access_count + 1,
                    last_accessed_at = ?
                WHERE id = ?
                """,
                (accessed_at, memory_id),
            )

    def search_memories(
        self,
        query_text: str,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[Memory]:
        # Escape LIKE wildcards in query_text
        escaped_query = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql = "SELECT * FROM memories WHERE content LIKE ? ESCAPE '\\'"
        params: list[Any] = [f"%{escaped_query}%"]

        if project_id:
            sql += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)

        sql += " ORDER BY importance DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetchall(sql, tuple(params))
        return [Memory.from_row(row) for row in rows]
