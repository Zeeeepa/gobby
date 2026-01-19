"""Memory backend factory.

This module provides a factory function for creating memory backends.
Users should use get_backend() to obtain a backend instance rather than
importing backend classes directly.

Example:
    from gobby.memory.backends import get_backend

    # Get SQLite backend with database connection
    backend = get_backend("sqlite", database=db)

    # Get null backend for testing
    test_backend = get_backend("null")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gobby.memory.protocol import MemoryBackendProtocol

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

__all__ = ["get_backend"]


def get_backend(backend_type: str, **kwargs: Any) -> MemoryBackendProtocol:
    """Create a memory backend instance.

    Factory function for creating memory backends. Use this instead of
    importing backend classes directly.

    Args:
        backend_type: Type of backend to create:
            - "sqlite": SQLite-based persistent storage (requires database kwarg)
            - "null": No-op backend for testing

        **kwargs: Backend-specific configuration:
            - database: DatabaseProtocol instance (required for "sqlite")

    Returns:
        A MemoryBackendProtocol instance

    Raises:
        ValueError: If backend_type is unknown or required kwargs are missing

    Example:
        # SQLite backend
        backend = get_backend("sqlite", database=my_db)

        # Null backend for testing
        test_backend = get_backend("null")
    """
    if backend_type == "sqlite":
        from gobby.memory.backends.sqlite import SQLiteBackend

        database: DatabaseProtocol | None = kwargs.get("database")
        if database is None:
            raise ValueError("SQLite backend requires 'database' parameter")
        return SQLiteBackend(database=database)

    elif backend_type == "null":
        from gobby.memory.backends.null import NullBackend

        return NullBackend()

    elif backend_type == "memu":
        from gobby.memory.backends.memu import MemUBackend

        api_key: str | None = kwargs.get("api_key")
        if api_key is None:
            raise ValueError("MemU backend requires 'api_key' parameter")
        return MemUBackend(
            api_key=api_key,
            user_id=kwargs.get("user_id"),
            org_id=kwargs.get("org_id"),
        )

    else:
        raise ValueError(
            f"Unknown backend type: '{backend_type}'. "
            f"Supported types: 'sqlite', 'null', 'memu'"
        )
