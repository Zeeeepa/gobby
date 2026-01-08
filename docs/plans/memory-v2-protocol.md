# Memory v2 Protocol: Pre-Launch Implementation

## Overview

This document covers the **immediate pre-launch work** to prepare Gobby's memory system for future cloud integration. The goal is to establish the backend abstraction pattern without changing any behavior—purely structural refactoring.

**Estimated effort: 6-10 hours**
**Risk: Low** (no behavior change, just structure)

## Goals

1. Define `MemoryBackend` protocol that any storage implementation can satisfy
2. Refactor current `MemoryManager` into `SQLiteBackend` implementing the protocol
3. Add config schema for future backend selection
4. Prepare database for segment-based memory tracking

## Non-Goals (Post-MVP)

- Implementing cloud backend
- Deploying infrastructure
- Billing integration
- Memory corrections/versioning

## Implementation

### 1. Define MemoryBackend Protocol

Create `src/gobby/memory/backends/__init__.py`:

```python
"""Memory backend protocol and factory."""

from typing import Protocol, runtime_checkable

from gobby.memory.models import Memory


@runtime_checkable
class MemoryBackend(Protocol):
    """
    Protocol for swappable memory backends.

    Implementations:
    - SQLiteBackend: Local storage (current behavior)
    - CloudBackend: Vector + Graph DB (future, Gobby Pro)
    """

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        tags: list[str] | None = None,
        source_type: str | None = None,
        source_session_id: str | None = None,
        supersedes: str | None = None,
    ) -> Memory:
        """
        Store a memory.

        Args:
            content: The memory content
            memory_type: One of 'fact', 'preference', 'pattern', 'context'
            importance: Float 0.0-1.0 for recall prioritization
            project_id: Scope to a project (None = global)
            tags: Optional categorization tags
            source_type: How memory was created ('user', 'session', 'workflow')
            source_session_id: Session that created this memory
            supersedes: If correcting a memory, the ID being replaced

        Returns:
            Created Memory object
        """
        ...

    async def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        use_semantic: bool = True,
        memory_type: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Memory]:
        """
        Retrieve relevant memories.

        Args:
            query: Search query (semantic if supported, else text)
            project_id: Filter to project (None includes global)
            limit: Maximum memories to return
            min_importance: Filter by minimum importance
            use_semantic: Use semantic search if available
            memory_type: Filter by type
            tags: Filter by tags

        Returns:
            List of matching Memory objects
        """
        ...

    async def forget(self, memory_id: str) -> bool:
        """
        Delete a memory.

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    async def get(self, memory_id: str) -> Memory | None:
        """
        Get a specific memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory object or None if not found
        """
        ...

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> Memory | None:
        """
        Update an existing memory.

        Args:
            memory_id: ID of memory to update
            content: New content (optional)
            importance: New importance (optional)
            tags: New tags (optional)

        Returns:
            Updated Memory or None if not found
        """
        ...

    def content_exists(self, content: str, project_id: str | None = None) -> bool:
        """
        Check if memory with this content already exists.

        Used for deduplication.

        Args:
            content: Content to check
            project_id: Project scope

        Returns:
            True if duplicate exists
        """
        ...

    def is_available(self) -> bool:
        """
        Check if backend is available and healthy.

        Used for graceful degradation.

        Returns:
            True if backend can accept requests
        """
        ...


def get_memory_backend(config) -> MemoryBackend:
    """
    Factory function to get the configured backend.

    Args:
        config: MemoryConfig with backend selection

    Returns:
        Configured MemoryBackend implementation
    """
    from gobby.memory.backends.sqlite import SQLiteBackend

    # Future: Check config.backend and return appropriate implementation
    # if config.backend == "cloud" and config.cloud and config.cloud.api_key:
    #     from gobby.memory.backends.cloud import CloudBackend
    #     backend = CloudBackend(config.cloud)
    #     if backend.is_available():
    #         return backend
    #     logger.warning("Cloud backend unavailable, falling back to SQLite")

    # Default: SQLite backend
    return SQLiteBackend(config)
```

### 2. Create SQLiteBackend

Create `src/gobby/memory/backends/sqlite.py`:

```python
"""SQLite-based memory backend (current implementation wrapped in protocol)."""

import logging

from gobby.config.app import MemoryConfig
from gobby.memory.backends import MemoryBackend
from gobby.memory.models import Memory
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager

logger = logging.getLogger(__name__)


class SQLiteBackend(MemoryBackend):
    """
    SQLite-based memory backend.

    This wraps the existing LocalMemoryManager to satisfy the MemoryBackend protocol.
    Behavior is unchanged from the current implementation.
    """

    def __init__(self, config: MemoryConfig, database: LocalDatabase | None = None):
        self.config = config
        self._db = database or LocalDatabase()
        self._storage = LocalMemoryManager(self._db)

        # Optional: embedding support for semantic search
        self._embedding_provider = None
        if config.embedding_model:
            # Future: Initialize embedding provider
            pass

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        tags: list[str] | None = None,
        source_type: str | None = None,
        source_session_id: str | None = None,
        supersedes: str | None = None,
    ) -> Memory:
        """Store a memory in SQLite."""
        # Delegate to existing storage
        return self._storage.create(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            tags=tags,
            source_type=source_type,
            source_session_id=source_session_id,
        )

    async def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        use_semantic: bool = True,
        memory_type: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Memory]:
        """Retrieve memories from SQLite."""
        # Delegate to existing search
        return self._storage.search(
            query=query,
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
            memory_type=memory_type,
        )

    async def forget(self, memory_id: str) -> bool:
        """Delete a memory from SQLite."""
        return self._storage.delete(memory_id)

    async def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID."""
        return self._storage.get(memory_id)

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> Memory | None:
        """Update a memory in SQLite."""
        return self._storage.update(
            memory_id=memory_id,
            content=content,
            importance=importance,
            tags=tags,
        )

    def content_exists(self, content: str, project_id: str | None = None) -> bool:
        """Check for duplicate content."""
        return self._storage.content_exists(content, project_id)

    def is_available(self) -> bool:
        """SQLite is always available (local file)."""
        return True
```

### 3. Refactor MemoryManager

Update `src/gobby/memory/manager.py` to use the backend:

```python
"""Memory manager using pluggable backends."""

import logging

from gobby.config.app import MemoryConfig
from gobby.memory.backends import MemoryBackend, get_memory_backend
from gobby.memory.models import Memory
from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    High-level memory manager.

    Delegates to a MemoryBackend for actual storage operations.
    Provides additional business logic like config-based filtering.
    """

    def __init__(
        self,
        database: LocalDatabase,
        config: MemoryConfig,
        backend: MemoryBackend | None = None,
    ):
        self._db = database
        self.config = config

        # Use provided backend or create from config
        self._backend = backend or get_memory_backend(config)

    @property
    def backend(self) -> MemoryBackend:
        """Access the underlying backend (for advanced use)."""
        return self._backend

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        tags: list[str] | None = None,
        source_type: str | None = None,
        source_session_id: str | None = None,
    ) -> Memory:
        """Store a memory."""
        if not self.config.enabled:
            raise RuntimeError("Memory system is disabled")

        return await self._backend.remember(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            tags=tags,
            source_type=source_type,
            source_session_id=source_session_id,
        )

    def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int | None = None,
        min_importance: float | None = None,
        use_semantic: bool = True,
    ) -> list[Memory]:
        """
        Retrieve relevant memories.

        Note: Synchronous wrapper for compatibility with existing code.
        """
        import asyncio

        if not self.config.enabled:
            return []

        # Use config defaults
        if limit is None:
            limit = self.config.injection_limit
        if min_importance is None:
            min_importance = self.config.importance_threshold

        # Run async method synchronously
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, use run_coroutine_threadsafe
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                self._backend.recall(
                    query=query,
                    project_id=project_id,
                    limit=limit,
                    min_importance=min_importance,
                    use_semantic=use_semantic,
                ),
                loop,
            )
            return future.result(timeout=10.0)
        except RuntimeError:
            # No event loop, run directly
            return asyncio.run(
                self._backend.recall(
                    query=query,
                    project_id=project_id,
                    limit=limit,
                    min_importance=min_importance,
                    use_semantic=use_semantic,
                )
            )

    async def forget(self, memory_id: str) -> bool:
        """Delete a memory."""
        return await self._backend.forget(memory_id)

    def content_exists(self, content: str, project_id: str | None = None) -> bool:
        """Check if content already exists (for deduplication)."""
        return self._backend.content_exists(content, project_id)

    def is_available(self) -> bool:
        """Check if memory system is available."""
        return self.config.enabled and self._backend.is_available()
```

### 4. Add Config Schema

Update `src/gobby/config/app.py`:

```python
@dataclass
class CloudMemoryConfig:
    """Configuration for cloud memory backend (Gobby Pro)."""
    api_url: str = "https://api.gobby.dev/v1"
    api_key: str | None = None  # From GOBBY_PRO_KEY env var
    timeout: float = 10.0
    retry_count: int = 3


@dataclass
class MemoryRecoveryConfig:
    """Configuration for memory recovery from crashed sessions."""
    enabled: bool = True
    check_interval_minutes: int = 10
    stale_session_timeout_minutes: int = 30


@dataclass
class MemoryConfig:
    """Memory system configuration."""
    enabled: bool = True
    backend: str = "sqlite"  # "sqlite" | "cloud"

    # Cloud backend (Gobby Pro)
    cloud: CloudMemoryConfig | None = None

    # Recovery settings
    recovery: MemoryRecoveryConfig | None = None

    # Existing settings
    auto_extract: bool = True
    injection_limit: int = 10
    importance_threshold: float = 0.3
    decay_enabled: bool = True
    decay_rate: float = 0.05
    decay_floor: float = 0.1
    embedding_model: str | None = None
    extraction_prompt: str = "..."  # existing default
```

### 5. Add Database Migration

Create migration for `memory_sync_index`:

```python
# In migrations.py or as separate migration file

def migrate_add_memory_sync_index(db: LocalDatabase) -> None:
    """Add memory_sync_index column to sessions table."""
    db.execute("""
        ALTER TABLE sessions
        ADD COLUMN memory_sync_index INTEGER DEFAULT 0
    """)
```

## File Changes Summary

| File | Change |
|------|--------|
| `src/gobby/memory/backends/__init__.py` | **NEW** - Protocol definition |
| `src/gobby/memory/backends/sqlite.py` | **NEW** - SQLite backend |
| `src/gobby/memory/manager.py` | **MODIFY** - Use backend |
| `src/gobby/config/app.py` | **MODIFY** - Add config classes |
| `src/gobby/storage/migrations.py` | **MODIFY** - Add migration |

## Testing

### Unit Tests

```python
# tests/memory/test_backends.py

import pytest
from gobby.memory.backends import MemoryBackend
from gobby.memory.backends.sqlite import SQLiteBackend


def test_sqlite_backend_implements_protocol():
    """SQLiteBackend satisfies MemoryBackend protocol."""
    assert isinstance(SQLiteBackend, type)
    # Protocol check
    backend = SQLiteBackend(config=...)
    assert isinstance(backend, MemoryBackend)


async def test_remember_and_recall():
    """Basic round-trip test."""
    backend = SQLiteBackend(config=...)

    memory = await backend.remember(
        content="Test fact",
        memory_type="fact",
        importance=0.8,
    )

    assert memory.id is not None
    assert memory.content == "Test fact"

    recalled = await backend.recall(query="Test")
    assert len(recalled) == 1
    assert recalled[0].id == memory.id


def test_backend_is_available():
    """SQLite backend is always available."""
    backend = SQLiteBackend(config=...)
    assert backend.is_available() is True
```

### Integration Tests

```python
# tests/memory/test_manager_backend.py

async def test_manager_uses_backend():
    """MemoryManager delegates to backend."""
    config = MemoryConfig(enabled=True, backend="sqlite")
    manager = MemoryManager(database=..., config=config)

    # Should use SQLiteBackend
    assert isinstance(manager.backend, SQLiteBackend)

    memory = await manager.remember(content="Test")
    assert memory is not None
```

## Checklist

### Phase 1: Protocol Definition
- [ ] Create `src/gobby/memory/backends/__init__.py` with `MemoryBackend` protocol
- [ ] Add `get_memory_backend()` factory function
- [ ] Add type hints and docstrings

### Phase 2: SQLite Backend
- [ ] Create `src/gobby/memory/backends/sqlite.py`
- [ ] Implement all protocol methods
- [ ] Wrap existing `LocalMemoryManager` calls
- [ ] Add `is_available()` (always returns True)

### Phase 3: Manager Refactor
- [ ] Update `MemoryManager.__init__` to accept/create backend
- [ ] Delegate all operations to backend
- [ ] Maintain sync/async compatibility
- [ ] Preserve existing public API

### Phase 4: Config Schema
- [ ] Add `CloudMemoryConfig` dataclass
- [ ] Add `MemoryRecoveryConfig` dataclass
- [ ] Update `MemoryConfig` with `backend` field
- [ ] Add env var support for `GOBBY_PRO_KEY`

### Phase 5: Database Prep
- [ ] Add migration for `memory_sync_index` column
- [ ] Test migration on existing databases

### Phase 6: Testing
- [ ] Unit tests for protocol compliance
- [ ] Integration tests for manager delegation
- [ ] Verify no behavior changes in existing code

## Success Criteria

1. **No behavior change**: All existing memory tests pass without modification
2. **Protocol satisfied**: `SQLiteBackend` is runtime-checkable as `MemoryBackend`
3. **Config ready**: Backend can be selected via config (only sqlite works for now)
4. **Migration works**: `memory_sync_index` column added without data loss

## Future Work (Not in this PR)

- Implement `CloudBackend` for Gobby Pro
- Add `memory_save_segment` workflow action
- Integrate with `SessionLifecycleManager` for recovery
- Build `gobby pro` CLI commands
