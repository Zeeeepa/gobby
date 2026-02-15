"""Workflow definition storage manager for local database."""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDefinitionRow:
    """Represents a workflow definition row from the database."""

    id: str
    name: str
    workflow_type: str
    enabled: bool
    priority: int
    definition_json: str
    source: str
    created_at: str
    updated_at: str
    project_id: str | None = None
    description: str | None = None
    version: str = "1.0"
    sources: list[str] | None = None
    tags: list[str] | None = None
    canvas_json: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "WorkflowDefinitionRow":
        def _parse_json_list(val: str | None) -> list[str] | None:
            if val is None:
                return None
            try:
                result = json.loads(val)
                return result if isinstance(result, list) else None
            except (json.JSONDecodeError, TypeError):
                return None

        return cls(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"],
            workflow_type=row["workflow_type"],
            version=row["version"] or "1.0",
            enabled=bool(row["enabled"]),
            priority=int(row["priority"]) if row["priority"] else 100,
            sources=_parse_json_list(row["sources"]),
            definition_json=row["definition_json"],
            canvas_json=row["canvas_json"],
            source=row["source"] or "custom",
            tags=_parse_json_list(row["tags"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "workflow_type": self.workflow_type,
            "version": self.version,
            "enabled": self.enabled,
            "priority": self.priority,
            "sources": self.sources,
            "definition_json": self.definition_json,
            "canvas_json": self.canvas_json,
            "source": self.source,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class LocalWorkflowDefinitionManager:
    """Manages workflow definitions in the local database."""

    def __init__(self, db: DatabaseProtocol):
        self.db = db

    def create(
        self,
        name: str,
        definition_json: str,
        workflow_type: str = "workflow",
        project_id: str | None = None,
        description: str | None = None,
        version: str = "1.0",
        enabled: bool = True,
        priority: int = 100,
        sources: list[str] | None = None,
        canvas_json: str | None = None,
        source: str = "custom",
        tags: list[str] | None = None,
    ) -> WorkflowDefinitionRow:
        """Create a new workflow definition in the database."""
        definition_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO workflow_definitions (
                    id, project_id, name, description, workflow_type,
                    version, enabled, priority, sources,
                    definition_json, canvas_json, source, tags,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition_id,
                    project_id,
                    name,
                    description,
                    workflow_type,
                    version,
                    1 if enabled else 0,
                    priority,
                    json.dumps(sources) if sources else None,
                    definition_json,
                    canvas_json,
                    source,
                    json.dumps(tags) if tags else None,
                    now,
                    now,
                ),
            )

        return self.get(definition_id)

    def get(self, definition_id: str) -> WorkflowDefinitionRow:
        """Get a workflow definition by primary key."""
        row = self.db.fetchone("SELECT * FROM workflow_definitions WHERE id = ?", (definition_id,))
        if not row:
            raise ValueError(f"Workflow definition {definition_id} not found")
        return WorkflowDefinitionRow.from_row(row)

    def get_by_name(self, name: str, project_id: str | None = None) -> WorkflowDefinitionRow | None:
        """Get a workflow definition by name (project-scoped first, then global fallback)."""
        if project_id:
            row = self.db.fetchone(
                "SELECT * FROM workflow_definitions WHERE name = ? AND project_id = ?",
                (name, project_id),
            )
            if row:
                return WorkflowDefinitionRow.from_row(row)
        # Fall back to global
        row = self.db.fetchone(
            "SELECT * FROM workflow_definitions WHERE name = ? AND project_id IS NULL",
            (name,),
        )
        return WorkflowDefinitionRow.from_row(row) if row else None

    def update(self, definition_id: str, **fields: Any) -> WorkflowDefinitionRow:
        """Partial update of a workflow definition."""
        json_fields = {"sources", "tags"}
        values: dict[str, Any] = {}
        for key, val in fields.items():
            if key in json_fields and val is not None:
                values[key] = json.dumps(val)
            elif key == "enabled" and isinstance(val, bool):
                values[key] = 1 if val else 0
            else:
                values[key] = val

        if not values:
            return self.get(definition_id)

        values["updated_at"] = datetime.now(UTC).isoformat()
        self.db.safe_update("workflow_definitions", values, "id = ?", (definition_id,))
        return self.get(definition_id)

    def delete(self, definition_id: str) -> bool:
        """Delete a workflow definition from the database."""
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM workflow_definitions WHERE id = ?", (definition_id,))
            return cursor.rowcount > 0

    def list_all(
        self,
        project_id: str | None = None,
        workflow_type: str | None = None,
        enabled: bool | None = None,
    ) -> list[WorkflowDefinitionRow]:
        """List workflow definitions with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if project_id:
            conditions.append("(project_id = ? OR project_id IS NULL)")
            params.append(project_id)

        if workflow_type:
            conditions.append("workflow_type = ?")
            params.append(workflow_type)

        if enabled is not None:
            conditions.append("enabled = ?")
            params.append(1 if enabled else 0)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.db.fetchall(
            f"SELECT * FROM workflow_definitions{where} ORDER BY name",
            tuple(params),
        )
        return [WorkflowDefinitionRow.from_row(r) for r in rows]

    def import_from_yaml(
        self, yaml_content: str, project_id: str | None = None
    ) -> WorkflowDefinitionRow:
        """Import a workflow definition from YAML content."""
        import yaml

        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict) or "name" not in data:
            raise ValueError("Invalid workflow YAML: must be a dict with 'name' field")

        name = data["name"]
        description = data.get("description", "")
        yaml_type = data.get("type", "")
        workflow_type = "pipeline" if yaml_type == "pipeline" else "workflow"
        version = str(data.get("version", "1.0"))
        enabled = bool(data.get("enabled", False))
        priority = data.get("priority", 100)
        sources_list = data.get("sources")

        return self.create(
            name=name,
            definition_json=json.dumps(data),
            workflow_type=workflow_type,
            project_id=project_id,
            description=description,
            version=version,
            enabled=enabled,
            priority=priority,
            sources=sources_list,
            source="imported",
        )

    def export_to_yaml(self, definition_id: str) -> str:
        """Export a workflow definition as YAML content."""
        import yaml

        row = self.get(definition_id)
        data = json.loads(row.definition_json)
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def duplicate(self, definition_id: str, new_name: str) -> WorkflowDefinitionRow:
        """Duplicate a workflow definition with a new name."""
        original = self.get(definition_id)
        definition_data = json.loads(original.definition_json)
        definition_data["name"] = new_name

        return self.create(
            name=new_name,
            definition_json=json.dumps(definition_data),
            workflow_type=original.workflow_type,
            project_id=original.project_id,
            description=original.description,
            version=original.version,
            enabled=original.enabled,
            priority=original.priority,
            sources=original.sources,
            canvas_json=original.canvas_json,
            source="custom",
            tags=original.tags,
        )
