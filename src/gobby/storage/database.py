"""SQLite database manager for local storage."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from gobby.storage.artifacts import LocalArtifactManager

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path.home() / ".gobby" / "gobby.db"

# SQL identifier validation pattern (alphanumeric + underscore only)
# Used by safe_update to prevent SQL injection via column/table names
_SQL_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class LocalDatabase:
    """
    SQLite database manager with connection pooling.

    Thread-safe connection management using thread-local storage.
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.gobby/gobby.db
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._local = threading.local()
        self._artifact_manager: LocalArtifactManager | None = None
        self._artifact_manager_lock = threading.Lock()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Create database directory if it doesn't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                isolation_level=None,  # Autocommit mode
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection.execute("PRAGMA journal_mode = WAL")
        return cast(sqlite3.Connection, self._local.connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """Get current thread's database connection."""
        return self._get_connection()

    @property
    def artifact_manager(self) -> LocalArtifactManager:
        """Get lazily-initialized LocalArtifactManager instance.

        The artifact manager is created on first access and reused for the
        lifetime of this LocalDatabase instance. Uses double-checked locking
        for thread-safe initialization.

        Returns:
            LocalArtifactManager instance for managing session artifacts.
        """
        if self._artifact_manager is None:
            with self._artifact_manager_lock:
                # Double-check inside lock
                if self._artifact_manager is None:
                    from gobby.storage.artifacts import LocalArtifactManager

                    self._artifact_manager = LocalArtifactManager(self)
        return self._artifact_manager

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute SQL statement."""
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        """Execute SQL statement with multiple parameter sets."""
        return self.connection.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """Execute query and fetch one row."""
        cursor = self.execute(sql, params)
        return cast(sqlite3.Row | None, cursor.fetchone())

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Execute query and fetch all rows."""
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def safe_update(
        self,
        table: str,
        values: dict[str, Any],
        where: str,
        where_params: tuple[Any, ...],
    ) -> sqlite3.Cursor:
        """
        Safely execute an UPDATE statement with dynamic columns.

        This method validates table and column names against a strict allowlist
        pattern to prevent SQL injection, even though callers typically use
        hardcoded strings. This is defense-in-depth.

        Args:
            table: Table name (validated against identifier pattern).
            values: Dictionary of column_name -> new_value.
            where: WHERE clause (e.g., "id = ?"). This is NOT validated -
                   callers must use parameterized queries for values.
            where_params: Parameters for the WHERE clause placeholders.

        Returns:
            sqlite3.Cursor from the executed statement.

        Raises:
            ValueError: If table or column names fail validation.

        Example:
            db.safe_update(
                "sessions",
                {"status": "closed", "updated_at": now},
                "id = ?",
                (session_id,)
            )
        """
        if not values:
            # No-op: return cursor without executing
            return self.connection.cursor()

        # Validate table name
        if not _SQL_IDENTIFIER_PATTERN.match(table):
            raise ValueError(f"Invalid table name: {table!r}")

        # Validate column names and build SET clause
        set_clauses: list[str] = []
        update_params: list[Any] = []

        for col, val in values.items():
            if not _SQL_IDENTIFIER_PATTERN.match(col):
                raise ValueError(f"Invalid column name: {col!r}")
            set_clauses.append(f"{col} = ?")
            update_params.append(val)

        # Construct and execute query
        # nosec B608: Table and column names are validated above against
        # a strict alphanumeric pattern. The WHERE clause uses parameterized
        # queries. This is safe from SQL injection.
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {where}"  # nosec B608
        full_params = tuple(update_params) + where_params

        return self.execute(sql, full_params)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Context manager for database transactions.

        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT ...")
                conn.execute("UPDATE ...")
        """
        conn = self.connection
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        """Close current thread's database connection and clean up managers."""
        # Clean up artifact manager
        self._artifact_manager = None

        # Close connection
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
