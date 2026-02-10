"""Memory backend factory.

This module provides a factory function for creating external memory backends.
The default SQLite storage is handled directly by MemoryManager via
LocalMemoryManager — it does not go through this factory.

Example:
    from gobby.memory.backends import get_backend

    # Get null backend for testing
    test_backend = get_backend("null")
"""

from __future__ import annotations

from typing import Any

from gobby.memory.protocol import MemoryBackendProtocol

__all__ = ["get_backend"]


def get_backend(backend_type: str, **kwargs: Any) -> MemoryBackendProtocol:
    """Create a memory backend instance.

    Factory function for creating external memory backends. Use this instead of
    importing backend classes directly.

    Note: SQLite storage is handled directly by MemoryManager and is not
    available through this factory.

    Args:
        backend_type: Type of backend to create:
            - "null": No-op backend for testing
            - "mem0": Mem0 cloud-based semantic memory (requires api_key kwarg)

        **kwargs: Backend-specific configuration:
            - api_key: API key (required for "mem0")
            - user_id: Default user ID (optional for "mem0")

    Returns:
        A MemoryBackendProtocol instance

    Raises:
        ValueError: If backend_type is unknown or required kwargs are missing

    Example:
        # Null backend for testing
        test_backend = get_backend("null")
    """
    if backend_type == "null":
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

    else:
        raise ValueError(
            f"Unknown backend type: '{backend_type}'. Supported types: 'null', 'mem0'"
        )
