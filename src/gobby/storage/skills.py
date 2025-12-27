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
class Skill:
    id: str
    name: str
    instructions: str
    created_at: str
    updated_at: str
    project_id: str | None = None
    description: str | None = None
    trigger_pattern: str | None = None
    source_session_id: str | None = None
    usage_count: int = 0
    success_rate: float | None = None
    tags: list[str] | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Skill":
        tags_json = row["tags"]
        tags = json.loads(tags_json) if tags_json else []

        return cls(
            id=row["id"],
            name=row["name"],
            instructions=row["instructions"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            project_id=row["project_id"],
            description=row["description"],
            trigger_pattern=row["trigger_pattern"],
            source_session_id=row["source_session_id"],
            usage_count=row["usage_count"],
            success_rate=row["success_rate"],
            tags=tags,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "instructions": self.instructions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project_id": self.project_id,
            "description": self.description,
            "trigger_pattern": self.trigger_pattern,
            "source_session_id": self.source_session_id,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "tags": self.tags,
        }


class LocalSkillManager:
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
                logger.error(f"Error in skill change listener: {e}")

    def create_skill(
        self,
        name: str,
        instructions: str,
        project_id: str | None = None,
        description: str | None = None,
        trigger_pattern: str | None = None,
        source_session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        now = datetime.now(UTC).isoformat()
        # ID based on name + project to ensure uniqueness/stability
        skill_id = generate_prefixed_id("sk", name + str(project_id))
        tags_json = json.dumps(tags) if tags else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO skills (
                    id, project_id, name, description, trigger_pattern,
                    instructions, source_session_id, usage_count, tags,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    skill_id,
                    project_id,
                    name,
                    description,
                    trigger_pattern,
                    instructions,
                    source_session_id,
                    tags_json,
                    now,
                    now,
                ),
            )

        self._notify_listeners()
        return self.get_skill(skill_id)

    def get_skill(self, skill_id: str) -> Skill:
        row = self.db.fetchone("SELECT * FROM skills WHERE id = ?", (skill_id,))
        if not row:
            raise ValueError(f"Skill {skill_id} not found")
        return Skill.from_row(row)

    def update_skill(
        self,
        skill_id: str,
        name: str | None = None,
        instructions: str | None = None,
        description: str | None = None,
        trigger_pattern: str | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        updates = []
        params: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if instructions is not None:
            updates.append("instructions = ?")
            params.append(instructions)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if trigger_pattern is not None:
            updates.append("trigger_pattern = ?")
            params.append(trigger_pattern)
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))

        if not updates:
            return self.get_skill(skill_id)

        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(skill_id)

        sql = f"UPDATE skills SET {', '.join(updates)} WHERE id = ?"

        with self.db.transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            if cursor.rowcount == 0:
                raise ValueError(f"Skill {skill_id} not found")

        self._notify_listeners()
        return self.get_skill(skill_id)

    def delete_skill(self, skill_id: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            if cursor.rowcount == 0:
                return False
        self._notify_listeners()
        return True

    def list_skills(
        self,
        project_id: str | None = None,
        name_like: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Skill]:
        query = "SELECT * FROM skills WHERE 1=1"
        params: list[Any] = []

        if project_id:
            query += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)

        if name_like:
            query += " AND name LIKE ?"
            params.append(f"%{name_like}%")

        query += " ORDER BY usage_count DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(query, tuple(params))
        return [Skill.from_row(row) for row in rows]
