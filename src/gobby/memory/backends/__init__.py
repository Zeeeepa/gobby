"""Memory backend factory.

This module provides a factory function for creating memory backends.

Note:
    - Default local storage is handled directly by MemoryManager via
      StorageAdapter wrapping LocalMemoryManager — it does not go through
      this factory.
    - This factory is primarily for testing (null backend) or future extensions.

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

    Factory function for creating memory backends. Currently only supports
    the "null" backend for testing.

    Note: Local storage uses StorageAdapter (via MemoryManager).

    Args:
        backend_type: Type of backend to create:
            - "null": No-op backend for testing

        **kwargs: Backend-specific configuration (unused for "null")

    Returns:
        A MemoryBackendProtocol instance

    Raises:
        ValueError: If backend_type is unknown

    Example:
        test_backend = get_backend("null")
    """
    if backend_type == "null":
        from gobby.memory.backends.null import NullBackend

        return NullBackend()

    else:
        raise ValueError(f"Unknown backend type: '{backend_type}'. Supported types: 'null'")
