"""SQLite database manager for local storage."""

from __future__ import annotations

import atexit
import logging
import os
import re
import sqlite3
import threading
import weakref
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

# Register custom datetime adapters/converters (required since Python 3.12)
# See: https://docs.python.org/3/library/sqlite3.html#default-adapters-and-converters-deprecated


def _adapt_datetime(val: datetime) -> str:
    """Adapt datetime to ISO format string for SQLite storage."""
    # If naive datetime, assume UTC and add timezone info for RFC3339 compliance
    if val.tzinfo is None:
        val = val.replace(tzinfo=UTC)
    return val.isoformat()


def _adapt_date(val: date) -> str:
    """Adapt date to ISO format string for SQLite storage."""
    return val.isoformat()


def _convert_datetime(val: bytes) -> datetime:
    """Convert SQLite datetime string back to datetime object."""
    dt = datetime.fromisoformat(val.decode())
    # Ensure timezone-aware (treat naive as UTC) for consistency
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _convert_date(val: bytes) -> date:
    """Convert SQLite date string back to date object."""
    return date.fromisoformat(val.decode())


# Register adapters (Python -> SQLite)
sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_adapter(date, _adapt_date)

# Register converters (SQLite -> Python) - used with detect_types
sqlite3.register_converter("datetime", _convert_datetime)
sqlite3.register_converter("date", _convert_date)

if TYPE_CHECKING:
    from gobby.storage.artifacts import LocalArtifactManager

logger = logging.getLogger(__name__)


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol defining the database interface for storage managers."""

    @property
    def db_path(self) -> Any:
        """Return database path."""
        ...

    @property
    def connection(self) -> sqlite3.Connection:
        """Get database connection (for reads)."""
        ...

    @property
    def artifact_manager(self) -> Any:
        """Get artifact manager."""
        ...

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute SQL statement."""
        ...

    def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        """Execute SQL statement with multiple parameter sets."""
        ...

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """Execute query and fetch one row."""
        ...

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Execute query and fetch all rows."""
        ...

    def safe_update(
        self,
        table: str,
        values: dict[str, Any],
        where: str,
        where_params: tuple[Any, ...],
    ) -> sqlite3.Cursor:
        """Safely execute an UPDATE statement with dynamic columns."""
        ...

    def transaction(self) -> AbstractContextManager[sqlite3.Connection]:
        """Context manager for database transactions."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...


# Default database path
DEFAULT_DB_PATH = Path.home() / ".gobby" / "gobby-hub.db"

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
            db_path: Path to SQLite database file. Defaults to ~/.gobby/gobby-hub.db
        """
        # SAFETY SWITCH: During tests, override with safe path from environment
        if db_path is None and os.environ.get("GOBBY_TEST_PROTECT") == "1":
            safe_path = os.environ.get("GOBBY_DATABASE_PATH")
            if safe_path:
                db_path = safe_path

        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._local = threading.local()
        self._artifact_manager: LocalArtifactManager | None = None
        self._artifact_manager_lock = threading.Lock()
        # Track all connections for proper cleanup across threads
        self._all_connections: set[sqlite3.Connection] = set()
        self._connections_lock = threading.Lock()
        self._ensure_directory()

        # Register atexit cleanup using weak reference to avoid preventing GC
        # and to safely handle shutdown without __del__ lock issues
        self._weak_self = weakref.ref(self)
        atexit.register(self._cleanup_at_exit)

    def _ensure_directory(self) -> None:
        """Create database directory if it doesn't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                isolation_level=None,  # Autocommit mode
            )
            conn.row_factory = sqlite3.Row
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            # Use default DELETE journal mode (more reliable than WAL for dual-write)
            self._local.connection = conn
            # Track for cleanup in close()
            with self._connections_lock:
                self._all_connections.add(conn)
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
        try:
            return cast(sqlite3.Row | None, cursor.fetchone())
        finally:
            cursor.close()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Execute query and fetch all rows."""
        cursor = self.execute(sql, params)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

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
            # No-op: return closed cursor without executing
            cursor = self.connection.cursor()
            cursor.close()
            return cursor

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
        # nosec B608: Table and column names are validated above against a strict alphanumeric pattern.
        # The WHERE clause uses parameterized queries. This is safe from SQL injection.
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
        """Close all database connections and clean up managers.

        Can be called explicitly or via context manager. For automatic cleanup
        at interpreter shutdown, atexit handler is used instead of __del__ to
        avoid lock acquisition issues during GC.
        """
        # Clean up artifact manager
        self._artifact_manager = None

        # Close all connections from all threads
        with self._connections_lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:
                    pass  # nosec B110 - connection may already be closed
            self._all_connections.clear()

        # Clear thread-local reference
        if hasattr(self._local, "connection"):
            self._local.connection = None

    def _cleanup_at_exit(self) -> None:
        """Atexit handler for safe cleanup during interpreter shutdown.

        Uses try/except to safely handle any errors that may occur during
        shutdown when modules may already be partially unloaded.
        """
        try:
            self.close()
        except Exception:
            pass  # nosec B110 - ignore errors during shutdown

    def __del__(self) -> None:
        """Clean up connections when object is garbage collected.

        Note: Most cleanup should happen via atexit or explicit close() calls.
        This is a fallback that unregisters the atexit handler to avoid double-close.
        """
        try:
            # Unregister atexit handler since we're being collected
            atexit.unregister(self._cleanup_at_exit)
        except Exception:
            pass  # nosec B110 - ignore errors during gc

    def __enter__(self) -> LocalDatabase:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        """Exit context manager, closing connections."""
        self.close()
