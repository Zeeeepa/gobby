"""Three-tier prompt storage.

Provides CRUD operations for prompt templates stored in SQLite.
Prompts have three tiers with precedence: project > user > bundled.
Follows the same pattern as RuleStore (storage/rules.py).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.storage.database import DatabaseProtocol

if TYPE_CHECKING:
    from gobby.prompts.models import PromptTemplate

logger = logging.getLogger(__name__)

VALID_TIERS = {"bundled", "user", "project"}
TIER_PRECEDENCE = ["project", "user", "bundled"]


@dataclass
class PromptRecord:
    """A prompt template record from the database."""

    id: str
    path: str
    name: str | None
    description: str
    version: str
    category: str
    content: str
    variables: dict[str, Any] | None
    tier: str
    project_id: str | None
    source_file: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PromptRecord:
        """Create a PromptRecord from a database row."""
        variables_json = row["variables"]
        variables = json.loads(variables_json) if variables_json else None

        return cls(
            id=row["id"],
            path=row["path"],
            name=row["name"],
            description=row["description"] or "",
            version=row["version"] or "1.0",
            category=row["category"],
            content=row["content"],
            variables=variables,
            tier=row["tier"],
            project_id=row["project_id"],
            source_file=row["source_file"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "path": self.path,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "content": self.content,
            "variables": self.variables,
            "tier": self.tier,
            "project_id": self.project_id,
            "source_file": self.source_file,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_template(self) -> PromptTemplate:
        """Convert to a PromptTemplate for use with the loader."""
        from gobby.prompts.models import PromptTemplate, VariableSpec

        variables: dict[str, VariableSpec] = {}
        if self.variables:
            for var_name, var_spec in self.variables.items():
                if isinstance(var_spec, dict):
                    variables[var_name] = VariableSpec(
                        type=var_spec.get("type", "str"),
                        default=var_spec.get("default"),
                        description=var_spec.get("description", ""),
                        required=var_spec.get("required", False),
                    )
                else:
                    variables[var_name] = VariableSpec(default=var_spec)

        return PromptTemplate(
            name=self.path,
            description=self.description,
            variables=variables,
            content=self.content,
            version=self.version,
        )


@dataclass
class SyncResult:
    """Result from a prompt sync operation."""

    synced: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "synced": self.synced,
            "updated": self.updated,
            "skipped": self.skipped,
            "removed": self.removed,
            "errors": self.errors,
        }


class LocalPromptManager:
    """CRUD operations for the three-tier prompt registry."""

    def __init__(self, db: DatabaseProtocol) -> None:
        self.db = db

    def save_prompt(
        self,
        path: str,
        content: str,
        tier: str,
        name: str | None = None,
        description: str = "",
        version: str = "1.0",
        category: str | None = None,
        variables: dict[str, Any] | None = None,
        project_id: str | None = None,
        source_file: str | None = None,
    ) -> PromptRecord:
        """Save a prompt (upsert by path+tier+project_id).

        Args:
            path: Prompt path (e.g. "expansion/system").
            content: Jinja2 template body (no frontmatter).
            tier: One of 'bundled', 'user', 'project'.
            name: Optional display name from frontmatter.
            description: Prompt description.
            version: Prompt version string.
            category: Derived from path prefix if not given.
            variables: JSON-serializable variable specs.
            project_id: Required for project-tier prompts.
            source_file: Original file path for bundled prompts.

        Returns:
            The saved PromptRecord.
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier '{tier}'. Must be one of: {VALID_TIERS}")

        if tier == "project" and not project_id:
            raise ValueError("project_id is required for project-tier prompts")

        if category is None:
            category = path.split("/")[0] if "/" in path else "general"

        now = datetime.now(UTC).isoformat()
        variables_json = json.dumps(variables) if variables else None
        coalesce_pid = project_id or ""

        existing = self.db.fetchone(
            """SELECT id FROM prompts
               WHERE path = ? AND tier = ? AND COALESCE(project_id, '') = ?""",
            (path, tier, coalesce_pid),
        )

        if existing:
            prompt_id = existing["id"]
            self.db.execute(
                """UPDATE prompts
                   SET name = ?, description = ?, version = ?, category = ?,
                       content = ?, variables = ?, source_file = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    name,
                    description,
                    version,
                    category,
                    content,
                    variables_json,
                    source_file,
                    now,
                    prompt_id,
                ),
            )
        else:
            prompt_id = str(uuid.uuid4())
            self.db.execute(
                """INSERT INTO prompts
                   (id, path, name, description, version, category, content,
                    variables, tier, project_id, source_file, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    prompt_id,
                    path,
                    name,
                    description,
                    version,
                    category,
                    content,
                    variables_json,
                    tier,
                    project_id,
                    source_file,
                    now,
                    now,
                ),
            )

        row = self.db.fetchone("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        assert row is not None, f"Prompt {prompt_id} not found after upsert"
        return PromptRecord.from_row(row)

    def get_prompt(
        self,
        path: str,
        project_id: str | None = None,
    ) -> PromptRecord | None:
        """Get a prompt by path, resolving tier precedence.

        Tier precedence: project > user > bundled.

        Args:
            path: Prompt path.
            project_id: Project ID (needed to find project-tier prompts).

        Returns:
            PromptRecord or None if not found.
        """
        tiers_to_check = TIER_PRECEDENCE if project_id else ["user", "bundled"]

        for tier in tiers_to_check:
            if tier == "project" and project_id:
                row = self.db.fetchone(
                    "SELECT * FROM prompts WHERE path = ? AND tier = ? AND project_id = ?",
                    (path, tier, project_id),
                )
            else:
                row = self.db.fetchone(
                    "SELECT * FROM prompts WHERE path = ? AND tier = ?",
                    (path, tier),
                )
            if row:
                return PromptRecord.from_row(row)

        return None

    def get_bundled(self, path: str) -> PromptRecord | None:
        """Always return the bundled-tier prompt (for diff/revert UI).

        Args:
            path: Prompt path.

        Returns:
            PromptRecord or None.
        """
        row = self.db.fetchone(
            "SELECT * FROM prompts WHERE path = ? AND tier = 'bundled'",
            (path,),
        )
        return PromptRecord.from_row(row) if row else None

    def list_prompts(
        self,
        category: str | None = None,
        tier: str | None = None,
        project_id: str | None = None,
    ) -> list[PromptRecord]:
        """List prompts, deduplicated by path with highest tier winning.

        Args:
            category: Filter by category.
            tier: If set, return only prompts from this tier.
            project_id: Project context for tier resolution.

        Returns:
            List of PromptRecord sorted by path.
        """
        if tier:
            # Direct tier query
            conditions = ["tier = ?"]
            params: list[Any] = [tier]
            if category:
                conditions.append("category = ?")
                params.append(category)
            if tier == "project" and project_id:
                conditions.append("project_id = ?")
                params.append(project_id)

            sql = f"SELECT * FROM prompts WHERE {' AND '.join(conditions)} ORDER BY path"  # nosec B608
            rows = self.db.fetchall(sql, tuple(params))
            return [PromptRecord.from_row(r) for r in rows]

        # Deduplicated: highest tier wins per path
        conditions_parts = []
        params_list: list[Any] = []

        if category:
            conditions_parts.append("category = ?")
            params_list.append(category)

        where_clause = f" WHERE {' AND '.join(conditions_parts)}" if conditions_parts else ""

        sql = f"SELECT * FROM prompts{where_clause} ORDER BY path, tier"  # nosec B608
        rows = self.db.fetchall(sql, tuple(params_list))

        # Deduplicate: for each path, pick highest priority tier
        best: dict[str, PromptRecord] = {}
        for row in rows:
            record = PromptRecord.from_row(row)
            # Skip project-tier prompts that don't match the project_id
            if record.tier == "project" and record.project_id != project_id:
                continue
            existing = best.get(record.path)
            if existing is None or _tier_rank(record.tier) < _tier_rank(existing.tier):
                best[record.path] = record

        return sorted(best.values(), key=lambda r: r.path)

    def delete_prompt(
        self,
        path: str,
        tier: str,
        project_id: str | None = None,
    ) -> bool:
        """Remove a prompt override.

        Args:
            path: Prompt path.
            tier: Tier to delete from.
            project_id: Project ID for project-tier.

        Returns:
            True if deleted, False if not found.
        """
        coalesce_pid = project_id or ""
        row = self.db.fetchone(
            """SELECT id FROM prompts
               WHERE path = ? AND tier = ? AND COALESCE(project_id, '') = ?""",
            (path, tier, coalesce_pid),
        )
        if not row:
            return False
        self.db.execute("DELETE FROM prompts WHERE id = ?", (row["id"],))
        return True

    def reset_to_bundled(
        self,
        path: str,
        project_id: str | None = None,
    ) -> bool:
        """Delete user and project overrides for a prompt path.

        Args:
            path: Prompt path.
            project_id: Project ID (to clear project-tier overrides).

        Returns:
            True if any overrides were deleted.
        """
        deleted = False
        if self.delete_prompt(path, "user"):
            deleted = True
        if project_id and self.delete_prompt(path, "project", project_id):
            deleted = True
        return deleted

    def list_bundled_paths(self) -> set[str]:
        """Return the set of all bundled prompt paths."""
        rows = self.db.fetchall("SELECT path FROM prompts WHERE tier = 'bundled'")
        return {row["path"] for row in rows}


def _tier_rank(tier: str) -> int:
    """Lower rank = higher priority."""
    try:
        return TIER_PRECEDENCE.index(tier)
    except ValueError:
        return 999
