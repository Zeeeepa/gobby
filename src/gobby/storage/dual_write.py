"""Dual-write database wrapper for project-local and hub databases."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)


class DualWriteConnection:
    """
    Wrapper around two SQLite connections that forwards writes to both.

    Used within DualWriteDatabase.transaction() to ensure writes
    within the transaction go to both databases. Duck-types as
    sqlite3.Connection for the execute/executemany methods.
    """

    def __init__(
        self,
        project_conn: sqlite3.Connection,
        hub_conn: sqlite3.Connection | None,
        log_hub_error: Any,
    ):
        self._project_conn = project_conn
        self._hub_conn = hub_conn
        self._log_hub_error = log_hub_error

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute SQL on both connections."""
        result = self._project_conn.execute(sql, params)
        if self._hub_conn is not None:
            try:
                self._hub_conn.execute(sql, params)
            except Exception as e:
                self._log_hub_error("transaction execute", e)
        return result

    def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        """Execute SQL with multiple params on both connections."""
        result = self._project_conn.executemany(sql, params_list)
        if self._hub_conn is not None:
            try:
                self._hub_conn.executemany(sql, params_list)
            except Exception as e:
                self._log_hub_error("transaction executemany", e)
        return result

    # Forward other common Connection methods to project connection
    def __getattr__(self, name: str) -> Any:
        """Forward unknown attributes to project connection."""
        return getattr(self._project_conn, name)


class DualWriteDatabase:
    """
    Database wrapper that writes to both project-local and hub databases.

    Writes go to project_db first, then hub_db. Hub failures are logged
    but not propagated (non-fatal). Reads always come from project_db.
    """

    def __init__(
        self,
        project_db: LocalDatabase,
        hub_db: LocalDatabase,
    ):
        """
        Initialize dual-write database.

        Args:
            project_db: Project-local database (primary, source of truth)
            hub_db: Global hub database (secondary, for cross-project queries)
        """
        self.project_db = project_db
        self.hub_db = hub_db
        self._hub_healthy = True

    @property
    def db_path(self) -> Any:
        """Return project database path (primary)."""
        return self.project_db.db_path

    @property
    def connection(self) -> sqlite3.Connection:
        """Get project database connection (for reads)."""
        return self.project_db.connection

    @property
    def hub_healthy(self) -> bool:
        """Check if hub database is healthy."""
        return self._hub_healthy

    @property
    def artifact_manager(self) -> Any:
        """Get artifact manager from project database."""
        return self.project_db.artifact_manager

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute SQL on both databases, return project result."""
        result = self.project_db.execute(sql, params)
        self._hub_execute(sql, params)
        return result

    def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        """Execute SQL with multiple params on both databases."""
        result = self.project_db.executemany(sql, params_list)
        self._hub_executemany(sql, params_list)
        return result

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """Fetch one row from project database only."""
        return self.project_db.fetchone(sql, params)

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Fetch all rows from project database only."""
        return self.project_db.fetchall(sql, params)

    def safe_update(
        self,
        table: str,
        values: dict[str, Any],
        where: str,
        where_params: tuple[Any, ...],
    ) -> sqlite3.Cursor:
        """Safely update on both databases."""
        result = self.project_db.safe_update(table, values, where, where_params)
        try:
            self.hub_db.safe_update(table, values, where, where_params)
        except Exception as e:
            self._log_hub_error("safe_update", e)
        return result

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Context manager for transactions on both databases.

        Yields a DualWriteConnection that forwards execute() calls to both
        project and hub connections. Commits/rollbacks are attempted on both,
        but hub failures don't affect the project transaction result.
        """
        # Start both transactions
        project_conn = self.project_db.connection
        project_conn.execute("BEGIN")

        hub_conn = self.hub_db.connection
        hub_in_transaction = False
        try:
            hub_conn.execute("BEGIN")
            hub_in_transaction = True
        except Exception as e:
            self._log_hub_error("transaction begin", e)

        # Create wrapper that forwards to both connections
        dual_conn = DualWriteConnection(
            project_conn,
            hub_conn if hub_in_transaction else None,
            self._log_hub_error,
        )

        try:
            # Cast to Connection for type compatibility - DualWriteConnection
            # duck-types as Connection via __getattr__
            yield cast(sqlite3.Connection, dual_conn)
            # Commit project first (primary)
            project_conn.execute("COMMIT")
            # Then hub (secondary)
            if hub_in_transaction and hub_conn is not None:
                try:
                    hub_conn.execute("COMMIT")
                except Exception as e:
                    self._log_hub_error("transaction commit", e)
        except Exception:
            # Rollback both
            project_conn.execute("ROLLBACK")
            if hub_in_transaction and hub_conn is not None:
                try:
                    hub_conn.execute("ROLLBACK")
                except Exception as e:
                    self._log_hub_error("transaction rollback", e)
            raise

    def close(self) -> None:
        """Close both database connections."""
        self.project_db.close()
        try:
            self.hub_db.close()
        except Exception as e:
            self._log_hub_error("close", e)

    def _hub_execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """Execute SQL on hub database, logging errors."""
        try:
            self.hub_db.execute(sql, params)
            self._hub_healthy = True
        except Exception as e:
            self._log_hub_error("execute", e)

    def _hub_executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        """Execute SQL with multiple params on hub database."""
        try:
            self.hub_db.executemany(sql, params_list)
            self._hub_healthy = True
        except Exception as e:
            self._log_hub_error("executemany", e)

    def _log_hub_error(self, operation: str, error: Exception) -> None:
        """Log hub database error and mark as unhealthy."""
        self._hub_healthy = False
        logger.warning(f"Hub database {operation} failed: {error}")
