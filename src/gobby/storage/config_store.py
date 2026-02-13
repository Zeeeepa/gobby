"""DB-first configuration storage.

Stores config key-value pairs in SQLite as flattened dotted paths.
Values are JSON-encoded so types are preserved (strings, bools, numbers, lists).

Resolution order: DB config_store > Pydantic defaults.
YAML serves as import/export only after one-time migration.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class ConfigStore:
    """Key-value config storage backed by SQLite.

    Keys are flattened dotted paths (e.g. "llm_providers.claude.models").
    Values are JSON-encoded for type preservation.
    """

    def __init__(self, db: DatabaseProtocol):
        self.db = db

    def get(self, key: str) -> Any | None:
        """Get a single config value, deserialized from JSON.

        Returns None if key doesn't exist.
        """
        row = self.db.fetchone("SELECT value FROM config_store WHERE key = ?", (key,))
        if not row:
            return None
        return json.loads(row["value"])

    def get_all(self) -> dict[str, Any]:
        """Get all config entries as flat key-value pairs."""
        rows = self.db.fetchall("SELECT key, value FROM config_store")
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def set(self, key: str, value: Any, source: str = "user") -> None:
        """Upsert a single config value (JSON-encoded)."""
        now = datetime.now(UTC).isoformat()
        json_value = json.dumps(value)
        self.db.execute(
            """INSERT INTO config_store (key, value, source, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   source = excluded.source,
                   updated_at = excluded.updated_at""",
            (key, json_value, source, now),
        )

    def set_many(self, entries: dict[str, Any], source: str = "user") -> int:
        """Bulk upsert config entries. Returns count of entries written."""
        now = datetime.now(UTC).isoformat()
        count = 0
        for key, value in entries.items():
            json_value = json.dumps(value)
            self.db.execute(
                """INSERT INTO config_store (key, value, source, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       source = excluded.source,
                       updated_at = excluded.updated_at""",
                (key, json_value, source, now),
            )
            count += 1
        return count

    def delete(self, key: str) -> bool:
        """Delete a single key. Returns True if it existed."""
        cursor = self.db.execute("DELETE FROM config_store WHERE key = ?", (key,))
        return bool(cursor.rowcount and cursor.rowcount > 0)

    def delete_all(self) -> int:
        """Delete all config entries. Returns count deleted."""
        cursor = self.db.execute("DELETE FROM config_store")
        return cursor.rowcount or 0

    def list_keys(self, prefix: str | None = None) -> list[str]:
        """List all keys, optionally filtered by prefix."""
        if prefix:
            rows = self.db.fetchall(
                "SELECT key FROM config_store WHERE key LIKE ? ORDER BY key",
                (f"{prefix}%",),
            )
        else:
            rows = self.db.fetchall("SELECT key FROM config_store ORDER BY key")
        return [row["key"] for row in rows]


# =============================================================================
# Flatten / unflatten utilities
# =============================================================================


def flatten_config(config_dict: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested config dict into dotted-path keys.

    Example:
        {"llm_providers": {"claude": {"enabled": True}}}
        → {"llm_providers.claude.enabled": True}

    Lists and non-dict values are kept as leaf values.
    """
    flat: dict[str, Any] = {}
    for key, value in config_dict.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            flat.update(flatten_config(value, full_key))
        else:
            flat[full_key] = value
    return flat


def unflatten_config(flat_dict: dict[str, Any]) -> dict[str, Any]:
    """Unflatten dotted-path keys back into a nested dict.

    Example:
        {"llm_providers.claude.enabled": True}
        → {"llm_providers": {"claude": {"enabled": True}}}
    """
    result: dict[str, Any] = {}
    for key, value in flat_dict.items():
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    return result
