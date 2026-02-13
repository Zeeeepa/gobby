"""Three-tier rule registry storage.

Provides CRUD operations for named rules stored in SQLite.
Rules have three tiers with precedence: project > user > bundled.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)

VALID_TIERS = {"bundled", "user", "project"}

# Tier precedence order (highest priority first)
TIER_PRECEDENCE = ["project", "user", "bundled"]


class RuleStore:
    """CRUD operations for the three-tier rule registry."""

    def __init__(self, db: DatabaseProtocol) -> None:
        self.db = db

    def save_rule(
        self,
        name: str,
        tier: str,
        definition: dict[str, Any],
        project_id: str | None = None,
        source_file: str | None = None,
    ) -> dict[str, Any]:
        """Save a rule (upsert by name+tier+project_id).

        Args:
            name: Rule name (unique within tier+project).
            tier: One of 'bundled', 'user', 'project'.
            definition: Rule definition dict (serialized as JSON).
            project_id: Required for project-tier rules.
            source_file: Optional file path this rule was synced from.

        Returns:
            Dict with rule fields including parsed definition.
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier '{tier}'. Must be one of: {VALID_TIERS}")

        if tier == "project" and not project_id:
            raise ValueError("project_id is required for project-tier rules")

        now = datetime.now(UTC).isoformat()
        definition_json = json.dumps(definition)

        # Check for existing rule with same name+tier+project_id
        coalesce_pid = project_id or ""
        existing = self.db.fetchone(
            """SELECT id FROM rules
               WHERE name = ? AND tier = ? AND COALESCE(project_id, '') = ?""",
            (name, tier, coalesce_pid),
        )

        if existing:
            rule_id = existing["id"]
            self.db.execute(
                """UPDATE rules
                   SET definition = ?, source_file = ?, updated_at = ?
                   WHERE id = ?""",
                (definition_json, source_file, now, rule_id),
            )
        else:
            rule_id = str(uuid.uuid4())
            self.db.execute(
                """INSERT INTO rules (id, name, tier, project_id, definition, source_file, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rule_id, name, tier, project_id, definition_json, source_file, now, now),
            )

        row = self.db.fetchone("SELECT * FROM rules WHERE id = ?", (rule_id,))
        return _row_to_dict(row)

    def get_rule(
        self,
        name: str,
        project_id: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any] | None:
        """Get a rule by name, resolving tier precedence.

        Tier precedence: project > user > bundled.
        If tier is specified, returns only from that tier.

        Args:
            name: Rule name.
            project_id: Project ID (needed to find project-tier rules).
            tier: If set, only look in this specific tier.

        Returns:
            Rule dict or None if not found.
        """
        if tier:
            if tier == "project" and not project_id:
                return None
            # Specific tier requested
            params: tuple[Any, ...] = (name, tier)
            sql = "SELECT * FROM rules WHERE name = ? AND tier = ?"
            if tier == "project" and project_id:
                sql += " AND project_id = ?"
                params = (name, tier, project_id)
            row = self.db.fetchone(sql, params)
            return _row_to_dict(row) if row else None

        # Resolve with tier precedence
        tiers_to_check = TIER_PRECEDENCE if project_id else ["user", "bundled"]

        for t in tiers_to_check:
            if t == "project" and project_id:
                row = self.db.fetchone(
                    "SELECT * FROM rules WHERE name = ? AND tier = ? AND project_id = ?",
                    (name, t, project_id),
                )
            else:
                row = self.db.fetchone(
                    "SELECT * FROM rules WHERE name = ? AND tier = ?",
                    (name, t),
                )
            if row:
                return _row_to_dict(row)

        return None

    def list_rules(
        self,
        tier: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List rules with optional filters.

        Args:
            tier: Filter by tier.
            project_id: Filter by project ID.

        Returns:
            List of rule dicts sorted by name.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if tier:
            conditions.append("tier = ?")
            params.append(tier)

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)

        sql = "SELECT * FROM rules"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY name"

        rows = self.db.fetchall(sql, tuple(params))
        return [_row_to_dict(row) for row in rows]

    def get_rules_by_tier(self, tier: str) -> list[dict[str, Any]]:
        """Get all rules in a specific tier.

        Args:
            tier: The tier to query.

        Returns:
            List of rule dicts sorted by name.
        """
        return self.list_rules(tier=tier)

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule by ID.

        Args:
            rule_id: Rule UUID.

        Returns:
            True if deleted, False if not found.
        """
        row = self.db.fetchone("SELECT id FROM rules WHERE id = ?", (rule_id,))
        if not row:
            return False
        self.db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        return True

    def delete_rule_by_name(
        self,
        name: str,
        tier: str,
        project_id: str | None = None,
    ) -> bool:
        """Delete a rule by name+tier+project_id.

        Args:
            name: Rule name.
            tier: Rule tier.
            project_id: Project ID (for project-tier rules).

        Returns:
            True if deleted, False if not found.
        """
        coalesce_pid = project_id or ""
        row = self.db.fetchone(
            """SELECT id FROM rules
               WHERE name = ? AND tier = ? AND COALESCE(project_id, '') = ?""",
            (name, tier, coalesce_pid),
        )
        if not row:
            return False
        self.db.execute("DELETE FROM rules WHERE id = ?", (row["id"],))
        return True


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a sqlite3.Row to a dict with parsed definition."""
    d = dict(row)
    if "definition" in d and isinstance(d["definition"], str):
        d["definition"] = json.loads(d["definition"])
    return d
