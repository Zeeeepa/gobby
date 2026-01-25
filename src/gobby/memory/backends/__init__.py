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
            - "mem0": Mem0 cloud-based semantic memory (requires api_key kwarg)
            - "memu": MemU structured memory (optional: database_type, llm_api_key)
            - "openmemory": Self-hosted OpenMemory REST API (requires base_url kwarg)

        **kwargs: Backend-specific configuration:
            - database: DatabaseProtocol instance (required for "sqlite")
            - api_key: API key (required for "mem0")
            - database_type: "inmemory", "sqlite", or "postgres" (for "memu")
            - database_url: Connection URL (for "memu" sqlite/postgres)
            - llm_api_key: LLM API key for embeddings (optional for "memu")
            - base_url: Server URL (required for "openmemory")
            - user_id: Default user ID (optional for "mem0", "memu", "openmemory")

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

    elif backend_type == "mem0":
        try:
            from gobby.memory.backends.mem0 import Mem0Backend
        except ImportError as e:
            raise ImportError(
                "mem0ai is not installed. Install with: pip install gobby[mem0]"
            ) from e

        api_key: str | None = kwargs.get("api_key")
        if api_key is None:
            raise ValueError("Mem0 backend requires 'api_key' parameter")
        return Mem0Backend(
            api_key=api_key,
            user_id=kwargs.get("user_id"),
            org_id=kwargs.get("org_id"),
        )

    elif backend_type == "memu":
        from gobby.memory.backends.memu import MemUBackend

        return MemUBackend(
            database_type=kwargs.get("database_type", "inmemory"),
            database_url=kwargs.get("database_url"),
            llm_api_key=kwargs.get("llm_api_key") or kwargs.get("api_key"),
            llm_base_url=kwargs.get("llm_base_url"),
            user_id=kwargs.get("user_id"),
        )

    elif backend_type == "openmemory":
        from gobby.memory.backends.openmemory import OpenMemoryBackend

        base_url: str | None = kwargs.get("base_url")
        if base_url is None:
            raise ValueError("OpenMemory backend requires 'base_url' parameter")
        return OpenMemoryBackend(
            base_url=base_url,
            api_key=kwargs.get("api_key"),
            user_id=kwargs.get("user_id"),
        )

    else:
        raise ValueError(
            f"Unknown backend type: '{backend_type}'. Supported types: 'sqlite', 'null', 'mem0', 'memu', 'openmemory'"
        )
