"""Agent definition storage manager for local database."""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinitionRow:
    """Represents an agent definition row from the database."""

    id: str
    name: str
    provider: str
    mode: str
    terminal: str
    base_branch: str
    timeout: float
    max_turns: int
    enabled: bool
    created_at: str
    updated_at: str
    project_id: str | None = None
    description: str | None = None
    model: str | None = None
    isolation: str | None = None
    default_workflow: str | None = None
    sandbox_config: dict[str, Any] | None = None
    skill_profile: dict[str, Any] | None = None
    workflows: dict[str, Any] | None = None
    lifecycle_variables: dict[str, Any] = field(default_factory=dict)
    default_variables: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "AgentDefinitionRow":
        def _parse_json(val: str | None) -> dict[str, Any] | None:
            if val is None:
                return None
            try:
                result: dict[str, Any] = json.loads(val)
                return result
            except (json.JSONDecodeError, TypeError):
                return None

        return cls(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"],
            provider=row["provider"],
            model=row["model"],
            mode=row["mode"],
            terminal=row["terminal"],
            isolation=row["isolation"],
            base_branch=row["base_branch"],
            timeout=float(row["timeout"]) if row["timeout"] else 120.0,
            max_turns=int(row["max_turns"]) if row["max_turns"] else 10,
            default_workflow=row["default_workflow"],
            sandbox_config=_parse_json(row["sandbox_config"]),
            skill_profile=_parse_json(row["skill_profile"]),
            workflows=_parse_json(row["workflows"]),
            lifecycle_variables=_parse_json(row["lifecycle_variables"]) or {},
            default_variables=_parse_json(row["default_variables"]) or {},
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
            "model": self.model,
            "mode": self.mode,
            "terminal": self.terminal,
            "isolation": self.isolation,
            "base_branch": self.base_branch,
            "timeout": self.timeout,
            "max_turns": self.max_turns,
            "default_workflow": self.default_workflow,
            "sandbox_config": self.sandbox_config,
            "skill_profile": self.skill_profile,
            "workflows": self.workflows,
            "lifecycle_variables": self.lifecycle_variables,
            "default_variables": self.default_variables,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class LocalAgentDefinitionManager:
    """Manages agent definitions in the local database."""

    def __init__(self, db: DatabaseProtocol):
        self.db = db

    def create(
        self,
        name: str,
        project_id: str | None = None,
        description: str | None = None,
        provider: str = "claude",
        model: str | None = None,
        mode: str = "headless",
        terminal: str = "auto",
        isolation: str | None = None,
        base_branch: str = "main",
        timeout: float = 120.0,
        max_turns: int = 10,
        default_workflow: str | None = None,
        sandbox_config: dict[str, Any] | None = None,
        skill_profile: dict[str, Any] | None = None,
        workflows: dict[str, Any] | None = None,
        lifecycle_variables: dict[str, Any] | None = None,
        default_variables: dict[str, Any] | None = None,
    ) -> AgentDefinitionRow:
        """Create a new agent definition in the database."""
        definition_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO agent_definitions (
                    id, project_id, name, description,
                    provider, model, mode, terminal, isolation, base_branch,
                    timeout, max_turns, default_workflow,
                    sandbox_config, skill_profile, workflows,
                    lifecycle_variables, default_variables,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    definition_id,
                    project_id,
                    name,
                    description,
                    provider,
                    model,
                    mode,
                    terminal,
                    isolation,
                    base_branch,
                    timeout,
                    max_turns,
                    default_workflow,
                    json.dumps(sandbox_config) if sandbox_config else None,
                    json.dumps(skill_profile) if skill_profile else None,
                    json.dumps(workflows) if workflows else None,
                    json.dumps(lifecycle_variables) if lifecycle_variables else None,
                    json.dumps(default_variables) if default_variables else None,
                    now,
                    now,
                ),
            )

        return self.get(definition_id)

    def get(self, definition_id: str) -> AgentDefinitionRow:
        """Get an agent definition by primary key."""
        row = self.db.fetchone(
            "SELECT * FROM agent_definitions WHERE id = ?", (definition_id,)
        )
        if not row:
            raise ValueError(f"Agent definition {definition_id} not found")
        return AgentDefinitionRow.from_row(row)

    def get_by_name(
        self, name: str, project_id: str | None = None
    ) -> AgentDefinitionRow | None:
        """Get an agent definition by name and scope (project first, then global)."""
        if project_id:
            row = self.db.fetchone(
                "SELECT * FROM agent_definitions WHERE name = ? AND project_id = ?",
                (name, project_id),
            )
            if row:
                return AgentDefinitionRow.from_row(row)
        # Fall back to global
        row = self.db.fetchone(
            "SELECT * FROM agent_definitions WHERE name = ? AND project_id IS NULL",
            (name,),
        )
        return AgentDefinitionRow.from_row(row) if row else None

    def update(self, definition_id: str, **fields: Any) -> AgentDefinitionRow:
        """Partial update of an agent definition."""
        json_fields = {
            "sandbox_config",
            "skill_profile",
            "workflows",
            "lifecycle_variables",
            "default_variables",
        }
        values: dict[str, Any] = {}
        for key, val in fields.items():
            if key in json_fields and val is not None:
                values[key] = json.dumps(val)
            else:
                values[key] = val

        if not values:
            return self.get(definition_id)

        values["updated_at"] = datetime.now(UTC).isoformat()
        self.db.safe_update("agent_definitions", values, "id = ?", (definition_id,))
        return self.get(definition_id)

    def delete(self, definition_id: str) -> bool:
        """Delete an agent definition from the database."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_definitions WHERE id = ?", (definition_id,)
            )
            return cursor.rowcount > 0

    def list_by_project(self, project_id: str) -> list[AgentDefinitionRow]:
        """List project-scoped agent definitions."""
        rows = self.db.fetchall(
            "SELECT * FROM agent_definitions WHERE project_id = ? ORDER BY name",
            (project_id,),
        )
        return [AgentDefinitionRow.from_row(r) for r in rows]

    def list_global(self) -> list[AgentDefinitionRow]:
        """List global agent templates (project_id IS NULL)."""
        rows = self.db.fetchall(
            "SELECT * FROM agent_definitions WHERE project_id IS NULL ORDER BY name",
        )
        return [AgentDefinitionRow.from_row(r) for r in rows]

    def list_all(self, project_id: str | None = None) -> list[AgentDefinitionRow]:
        """List all agent definitions (project-scoped + global)."""
        if project_id:
            rows = self.db.fetchall(
                """SELECT * FROM agent_definitions
                WHERE project_id = ? OR project_id IS NULL
                ORDER BY name""",
                (project_id,),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM agent_definitions ORDER BY name",
            )
        return [AgentDefinitionRow.from_row(r) for r in rows]

    def import_from_definition(
        self, agent_def: Any, project_id: str | None = None
    ) -> AgentDefinitionRow:
        """Import an AgentDefinition Pydantic model into the database."""
        from gobby.agents.definitions import AgentDefinition

        if not isinstance(agent_def, AgentDefinition):
            raise TypeError(f"Expected AgentDefinition, got {type(agent_def)}")

        workflows_dict = None
        if agent_def.workflows:
            workflows_dict = {
                name: spec.model_dump(exclude_none=True)
                for name, spec in agent_def.workflows.items()
            }

        sandbox_dict = agent_def.sandbox.model_dump() if agent_def.sandbox else None
        skill_dict = (
            agent_def.skill_profile.model_dump() if agent_def.skill_profile else None
        )

        return self.create(
            name=agent_def.name,
            project_id=project_id,
            description=agent_def.description,
            provider=agent_def.provider,
            model=agent_def.model,
            mode=agent_def.mode,
            terminal=agent_def.terminal,
            isolation=agent_def.isolation,
            base_branch=agent_def.base_branch,
            timeout=agent_def.timeout,
            max_turns=agent_def.max_turns,
            default_workflow=agent_def.default_workflow,
            sandbox_config=sandbox_dict,
            skill_profile=skill_dict,
            workflows=workflows_dict,
            lifecycle_variables=agent_def.lifecycle_variables or None,
            default_variables=agent_def.default_variables or None,
        )

    def export_to_definition(self, definition_id: str) -> Any:
        """Export a DB row back to an AgentDefinition Pydantic model."""
        from gobby.agents.definitions import AgentDefinition

        row = self.get(definition_id)
        data: dict[str, Any] = {
            "name": row.name,
            "provider": row.provider,
            "mode": row.mode,
            "terminal": row.terminal,
            "base_branch": row.base_branch,
            "timeout": row.timeout,
            "max_turns": row.max_turns,
        }
        if row.description:
            data["description"] = row.description
        if row.model:
            data["model"] = row.model
        if row.isolation:
            data["isolation"] = row.isolation
        if row.default_workflow:
            data["default_workflow"] = row.default_workflow
        if row.sandbox_config:
            data["sandbox"] = row.sandbox_config
        if row.skill_profile:
            data["skill_profile"] = row.skill_profile
        if row.workflows:
            data["workflows"] = row.workflows
        if row.lifecycle_variables:
            data["lifecycle_variables"] = row.lifecycle_variables
        if row.default_variables:
            data["default_variables"] = row.default_variables

        return AgentDefinition(**data)
