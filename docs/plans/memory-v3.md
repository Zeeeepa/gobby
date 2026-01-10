# Memory V3: Backend Abstraction Layer

## Overview

Memory V3 transforms gobby-memory from a monolithic implementation into a **pluggable abstraction layer** that can integrate with external memory systems. Users can choose between Gobby's built-in SQLite backend, or plug in established memory frameworks like MemU or Mem0.

**Strategic rationale:** Like Microsoft making Excel compatible with Lotus 1-2-3, reducing switching costs accelerates adoption. Users already invested in Mem0 or MemU can use Gobby's orchestration layer without migrating their memory infrastructure.

**Key changes:**

- **Backend protocol** - Standardized interface for memory operations
- **Pluggable backends** - SQLite (built-in), MemU, Mem0, custom
- **Multimodal support** - Image attachments for browser automation (Playwright, Puppeteer)
- **Markdown sync** - MemU-style git-friendly category files
- **Capability detection** - Graceful degradation for feature differences

**What stays the same:**

- MCP tool interface (`remember`, `recall`, `forget`, etc.)
- Workflow integration and hooks
- Session linking and project scoping
- CLI commands

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     GOBBY ORCHESTRATION                        │
│          (sessions, hooks, workflows, agents, tasks)           │
└───────────────────────────┬────────────────────────────────────┘
                            │
                   ┌────────▼────────┐
                   │  MemoryManager  │  ← High-level API
                   │   (facade)      │    Capability-aware
                   └────────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
         ┌────▼────┐  ┌─────▼─────┐  ┌────▼────┐
         │ SQLite  │  │   MemU    │  │  Mem0   │
         │ Backend │  │  Backend  │  │ Backend │
         └────┬────┘  └─────┬─────┘  └────┬────┘
              │             │             │
         "built-in"    "hierarchical"  "enterprise"
         "zero-config"  "git-native"   "popular"
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `MemoryManager` | High-level API, capability adaptation, multimodal helpers |
| `MemoryBackend` (protocol) | Contract all backends implement |
| `SqliteMemoryBackend` | Current implementation, refactored |
| `MemuMemoryBackend` | Integration with MemU framework |
| `Mem0MemoryBackend` | Integration with Mem0 framework |
| `NullMemoryBackend` | No-op for testing/disabled memory |

## Backend Protocol

### Core Types

```python
# src/gobby/memory/protocol.py

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import Protocol, runtime_checkable


class MemoryCapability(Flag):
    """Capabilities a backend may support. Backends declare what they provide."""

    # Core operations
    BASIC = auto()              # remember, recall, forget, get
    UPDATE = auto()             # update existing memories

    # Search modes
    SEMANTIC_SEARCH = auto()    # Embedding-based similarity search
    KEYWORD_SEARCH = auto()     # BM25/TF-IDF text search
    HYBRID_SEARCH = auto()      # Combined semantic + keyword

    # Multimodal
    IMAGES = auto()             # Image attachments
    AUDIO = auto()              # Audio attachments (future)
    DOCUMENTS = auto()          # Document attachments (PDF, etc.)

    # Organization
    CATEGORIES = auto()         # Hierarchical organization (MemU-style)
    TAGS = auto()               # Tag-based filtering
    CROSS_REFERENCES = auto()   # Auto-linking related memories

    # Maintenance
    IMPORTANCE_DECAY = auto()   # Automatic importance decay over time
    DEDUPLICATION = auto()      # Semantic duplicate detection

    # Sync
    SYNC_JSONL = auto()         # JSONL file export/import
    SYNC_MARKDOWN = auto()      # Markdown category files (git-friendly)


@dataclass
class MemoryQuery:
    """
    Unified query object for memory retrieval.

    Backends handle the subset of fields they support.
    Unknown fields are ignored gracefully.
    """
    text: str | None = None              # Query string for search
    memory_type: str | None = None       # Filter: fact, preference, pattern, context
    min_importance: float = 0.0          # Minimum importance threshold
    max_importance: float = 1.0          # Maximum importance threshold
    tags_all: list[str] | None = None    # Must have ALL these tags
    tags_any: list[str] | None = None    # Must have at least ONE of these tags
    tags_none: list[str] | None = None   # Must NOT have any of these tags
    project_id: str | None = None        # Scope to specific project
    include_global: bool = True          # Include project_id=NULL memories
    limit: int = 10                       # Max results
    offset: int = 0                       # Pagination offset

    # Backend-specific (may be ignored)
    category: str | None = None          # MemU: filter by category
    search_mode: str = "auto"            # "semantic", "keyword", "hybrid", "auto"
    min_similarity: float = 0.0          # Minimum similarity for semantic search


@dataclass
class MediaAttachment:
    """
    Attachment for multimodal memories (images, audio, documents).

    Storage modes:
    - "file": reference is a file path (relative to project or absolute)
    - "url": reference is an HTTP(S) URL
    - "inline": reference is base64-encoded data (small files only)
    """
    media_type: str                      # "image", "audio", "document"
    mime_type: str                       # "image/png", "audio/wav", "application/pdf"
    reference: str                       # File path, URL, or base64 data
    storage_mode: str = "file"           # "file", "url", "inline"
    description: str | None = None       # Text description for searchability
    width: int | None = None             # Image width (if applicable)
    height: int | None = None            # Image height (if applicable)

    def to_dict(self) -> dict:
        return {
            "media_type": self.media_type,
            "mime_type": self.mime_type,
            "reference": self.reference,
            "storage_mode": self.storage_mode,
            "description": self.description,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MediaAttachment":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MemoryRecord:
    """
    Normalized memory representation across all backends.

    This is the canonical format returned by all backend operations.
    Backend-specific fields are preserved in `backend_metadata` for round-tripping.
    """
    id: str                                        # Unique identifier
    content: str                                   # Memory text content
    memory_type: str                               # fact, preference, pattern, context
    importance: float                              # 0.0-1.0
    tags: list[str] = field(default_factory=list) # Tag list
    created_at: str = ""                           # ISO timestamp
    updated_at: str = ""                           # ISO timestamp
    project_id: str | None = None                  # NULL for global memories
    source_type: str | None = None                 # user, session, skill, inferred
    source_session_id: str | None = None          # Session that created this
    access_count: int = 0                          # Times retrieved
    last_accessed_at: str | None = None           # Last access timestamp

    # Multimodal
    media: list[MediaAttachment] = field(default_factory=list)

    # Search result metadata (populated by recall)
    similarity_score: float | None = None          # 0.0-1.0 if from semantic search

    # Backend-specific (preserved for round-tripping)
    category: str | None = None                    # MemU: category assignment
    backend_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project_id": self.project_id,
            "source_type": self.source_type,
            "source_session_id": self.source_session_id,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at,
        }
        if self.media:
            result["media"] = [m.to_dict() for m in self.media]
        if self.similarity_score is not None:
            result["similarity_score"] = self.similarity_score
        if self.category:
            result["category"] = self.category
        if self.backend_metadata:
            result["backend_metadata"] = self.backend_metadata
        return result
```

### Backend Protocol

```python
@runtime_checkable
class MemoryBackend(Protocol):
    """
    Core protocol all memory backends must implement.

    Backends declare their capabilities via the `capabilities` property.
    The MemoryManager adapts behavior based on available capabilities.
    """

    @property
    def capabilities(self) -> MemoryCapability:
        """Declare what this backend supports."""
        ...

    @property
    def name(self) -> str:
        """Human-readable backend name for logging/debugging."""
        ...

    # === Core Operations (BASIC capability) ===

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        tags: list[str] | None = None,
        project_id: str | None = None,
        source_type: str | None = None,
        source_session_id: str | None = None,
        media: list[MediaAttachment] | None = None,
        category: str | None = None,
    ) -> MemoryRecord:
        """
        Store a new memory.

        Args:
            content: The memory text content
            memory_type: One of: fact, preference, pattern, context
            importance: Priority for recall (0.0-1.0)
            tags: Optional tag list for filtering
            project_id: Project scope (NULL for global)
            source_type: Origin of memory (user, session, skill, inferred)
            source_session_id: Session that created this memory
            media: Multimodal attachments (requires IMAGES/AUDIO capability)
            category: Category assignment (requires CATEGORIES capability)

        Returns:
            The created MemoryRecord with generated ID
        """
        ...

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        """
        Retrieve memories matching the query.

        Search behavior depends on capabilities:
        - SEMANTIC_SEARCH: Uses embeddings for similarity
        - KEYWORD_SEARCH: Uses BM25/TF-IDF
        - HYBRID_SEARCH: Combines both with RRF
        - None of above: Falls back to exact text match

        Returns:
            List of matching memories, sorted by relevance
        """
        ...

    async def forget(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.

        Returns:
            True if memory was deleted, False if not found
        """
        ...

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """
        Get a specific memory by ID.

        Returns:
            The memory if found, None otherwise
        """
        ...

    # === Extended Operations (optional capabilities) ===

    async def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        media: list[MediaAttachment] | None = None,
        category: str | None = None,
    ) -> MemoryRecord | None:
        """
        Update an existing memory. Requires UPDATE capability.

        Only non-None fields are updated.

        Returns:
            Updated memory if found, None otherwise
        """
        ...

    async def list_memories(
        self,
        project_id: str | None = None,
        memory_type: str | None = None,
        min_importance: float = 0.0,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """
        List memories with basic filtering (no search).

        Returns:
            List of memories sorted by importance DESC, created_at DESC
        """
        ...

    async def count(
        self,
        project_id: str | None = None,
        memory_type: str | None = None,
    ) -> int:
        """
        Count memories matching filters.
        """
        ...

    # === Capability-Specific Operations ===

    async def find_duplicates(
        self,
        content: str,
        threshold: float = 0.9,
        project_id: str | None = None,
    ) -> list[MemoryRecord]:
        """
        Find semantically similar memories. Requires DEDUPLICATION capability.

        Args:
            content: Content to check for duplicates
            threshold: Minimum similarity (0.0-1.0)
            project_id: Scope to project

        Returns:
            List of similar memories with similarity_score populated
        """
        ...

    async def decay_importance(
        self,
        decay_rate: float = 0.05,
        decay_floor: float = 0.1,
        max_age_days: int = 30,
    ) -> int:
        """
        Decay importance of old, unused memories. Requires IMPORTANCE_DECAY capability.

        Returns:
            Number of memories affected
        """
        ...

    async def categorize(
        self,
        memory_id: str,
        category: str,
    ) -> MemoryRecord | None:
        """
        Assign memory to a category. Requires CATEGORIES capability.

        Returns:
            Updated memory if found, None otherwise
        """
        ...

    async def list_categories(
        self,
        project_id: str | None = None,
    ) -> list[str]:
        """
        List available categories. Requires CATEGORIES capability.
        """
        ...

    async def get_related(
        self,
        memory_id: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """
        Get memories related to this one. Requires CROSS_REFERENCES capability.

        Returns:
            Related memories with similarity_score populated
        """
        ...

    # === Sync Operations ===

    async def export_jsonl(
        self,
        path: str,
        project_id: str | None = None,
    ) -> int:
        """
        Export memories to JSONL file. Requires SYNC_JSONL capability.

        Returns:
            Number of memories exported
        """
        ...

    async def import_jsonl(
        self,
        path: str,
        project_id: str | None = None,
    ) -> tuple[int, int]:
        """
        Import memories from JSONL file. Requires SYNC_JSONL capability.

        Returns:
            Tuple of (created_count, updated_count)
        """
        ...

    async def export_markdown(
        self,
        directory: str,
        project_id: str | None = None,
    ) -> int:
        """
        Export memories to markdown category files. Requires SYNC_MARKDOWN capability.

        Directory structure:
            {directory}/
            ├── preferences.md
            ├── facts.md
            ├── patterns.md
            ├── context.md
            └── resources/
                └── {attachment files}

        Returns:
            Number of memories exported
        """
        ...

    async def import_markdown(
        self,
        directory: str,
        project_id: str | None = None,
    ) -> tuple[int, int]:
        """
        Import memories from markdown category files. Requires SYNC_MARKDOWN capability.

        Returns:
            Tuple of (created_count, updated_count)
        """
        ...

    # === Lifecycle ===

    async def initialize(self) -> None:
        """
        Initialize the backend (create tables, connect to services, etc.).
        Called once at startup.
        """
        ...

    async def shutdown(self) -> None:
        """
        Clean shutdown (close connections, flush caches, etc.).
        """
        ...

    async def health_check(self) -> dict:
        """
        Check backend health.

        Returns:
            Dict with "healthy" bool and optional "details" dict
        """
        ...
```

## Backend Implementations

### SQLite Backend (Built-in)

Refactors current implementation to implement the protocol.

```python
# src/gobby/memory/backends/sqlite.py

class SqliteMemoryBackend:
    """
    Built-in SQLite backend. Zero external dependencies.

    This is the default backend that works out of the box.
    """

    def __init__(
        self,
        db_path: str | None = None,
        semantic_search_enabled: bool = True,
        embedding_provider: str = "openai",
        embedding_model: str = "text-embedding-3-small",
        tfidf_enabled: bool = True,
        decay_enabled: bool = True,
        images_enabled: bool = True,
        resources_path: str = ".gobby/resources",
        markdown_sync_enabled: bool = False,
    ):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._semantic_enabled = semantic_search_enabled
        self._tfidf_enabled = tfidf_enabled
        self._decay_enabled = decay_enabled
        self._images_enabled = images_enabled
        self._resources_path = resources_path
        self._markdown_sync = markdown_sync_enabled

        # Lazy-loaded components
        self._storage: LocalMemoryManager | None = None
        self._semantic_search: SemanticMemorySearch | None = None
        self._tfidf_search: TFIDFSearcher | None = None

    @property
    def capabilities(self) -> MemoryCapability:
        caps = (
            MemoryCapability.BASIC |
            MemoryCapability.UPDATE |
            MemoryCapability.TAGS |
            MemoryCapability.SYNC_JSONL
        )
        if self._semantic_enabled:
            caps |= MemoryCapability.SEMANTIC_SEARCH
            caps |= MemoryCapability.DEDUPLICATION
        if self._tfidf_enabled:
            caps |= MemoryCapability.KEYWORD_SEARCH
        if self._semantic_enabled and self._tfidf_enabled:
            caps |= MemoryCapability.HYBRID_SEARCH
        if self._decay_enabled:
            caps |= MemoryCapability.IMPORTANCE_DECAY
        if self._images_enabled:
            caps |= MemoryCapability.IMAGES
        if self._markdown_sync:
            caps |= MemoryCapability.SYNC_MARKDOWN
        return caps

    @property
    def name(self) -> str:
        return "sqlite"

    # ... implementation wraps existing LocalMemoryManager + SemanticMemorySearch
```

**Key changes from current implementation:**

1. Extract to separate `backends/` package
2. Implement full `MemoryBackend` protocol
3. Add `MediaAttachment` support (new `media` JSON column)
4. Add optional markdown export alongside JSONL
5. Integrate TF-IDF search from V2 plan

### MemU Backend

```python
# src/gobby/memory/backends/memu.py

class MemuMemoryBackend:
    """
    Backend for MemU (https://github.com/NevaMind-AI/memU).

    MemU provides:
    - Hierarchical memory organization (Resource → Item → Category)
    - Markdown-based storage (git-friendly)
    - Multimodal support (images, audio, video)
    - Dual retrieval (embedding + LLM-based)
    - Self-evolving memory categories

    Requires: pip install memu-py
    """

    def __init__(
        self,
        mode: str = "embedded",           # "embedded" or "server"
        server_url: str | None = None,    # For server mode
        categories_path: str = ".gobby/memory",
        resources_path: str = ".gobby/memory/resources",
        auto_categorize: bool = True,
        llm_retrieval_enabled: bool = True,
    ):
        self._mode = mode
        self._server_url = server_url
        self._categories_path = categories_path
        self._resources_path = resources_path
        self._auto_categorize = auto_categorize
        self._llm_retrieval = llm_retrieval_enabled
        self._client = None

    @property
    def capabilities(self) -> MemoryCapability:
        return (
            MemoryCapability.BASIC |
            MemoryCapability.UPDATE |
            MemoryCapability.SEMANTIC_SEARCH |
            MemoryCapability.KEYWORD_SEARCH |
            MemoryCapability.HYBRID_SEARCH |
            MemoryCapability.IMAGES |
            MemoryCapability.AUDIO |
            MemoryCapability.DOCUMENTS |
            MemoryCapability.CATEGORIES |
            MemoryCapability.TAGS |
            MemoryCapability.DEDUPLICATION |
            MemoryCapability.SYNC_MARKDOWN
        )

    @property
    def name(self) -> str:
        return "memu"

    async def initialize(self) -> None:
        try:
            from memu import MemuClient  # Lazy import
        except ImportError:
            raise ImportError(
                "MemU backend requires memu-py. Install with: pip install memu-py"
            )

        if self._mode == "embedded":
            self._client = MemuClient(
                storage_path=self._categories_path,
                resources_path=self._resources_path,
            )
        else:
            self._client = MemuClient.connect(self._server_url)

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        media: list[MediaAttachment] | None = None,
        category: str | None = None,
        **kwargs,
    ) -> MemoryRecord:
        # Handle multimodal - MemU stores resources separately
        resource_ids = []
        if media:
            for attachment in media:
                resource_id = await self._upload_resource(attachment)
                resource_ids.append(resource_id)

        # MemU auto-categorizes if category not specified
        target_category = category or self._infer_category(memory_type)

        result = await self._client.create_memory(
            content=content,
            category=target_category,
            resource_ids=resource_ids,
            metadata={
                "memory_type": memory_type,
                "importance": kwargs.get("importance", 0.5),
                "tags": kwargs.get("tags", []),
                "project_id": kwargs.get("project_id"),
                "source_type": kwargs.get("source_type"),
                "source_session_id": kwargs.get("source_session_id"),
            },
        )

        return self._to_record(result)

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        # MemU supports dual retrieval
        if query.search_mode == "auto":
            # Use MemU's intelligent routing
            results = await self._client.search(
                query=query.text,
                category=query.category,
                limit=query.limit,
                use_llm=self._llm_retrieval,
            )
        elif query.search_mode == "semantic":
            results = await self._client.semantic_search(
                query=query.text,
                limit=query.limit,
            )
        else:  # keyword
            results = await self._client.bm25_search(
                query=query.text,
                limit=query.limit,
            )

        # Filter by project_id and other criteria
        records = [self._to_record(r) for r in results]
        return self._apply_filters(records, query)

    async def categorize(
        self,
        memory_id: str,
        category: str,
    ) -> MemoryRecord | None:
        # MemU native operation - moves memory to category file
        result = await self._client.move_to_category(memory_id, category)
        return self._to_record(result) if result else None

    async def list_categories(
        self,
        project_id: str | None = None,
    ) -> list[str]:
        # MemU stores categories as markdown files
        categories = await self._client.list_categories()
        return [c.name for c in categories]

    def _to_record(self, memu_item) -> MemoryRecord:
        """Convert MemU item to normalized MemoryRecord."""
        return MemoryRecord(
            id=memu_item.id,
            content=memu_item.content,
            memory_type=memu_item.metadata.get("memory_type", "fact"),
            importance=memu_item.metadata.get("importance", 0.5),
            tags=memu_item.metadata.get("tags", []),
            created_at=memu_item.created_at,
            updated_at=memu_item.updated_at,
            project_id=memu_item.metadata.get("project_id"),
            source_type=memu_item.metadata.get("source_type"),
            source_session_id=memu_item.metadata.get("source_session_id"),
            category=memu_item.category,
            media=self._convert_resources(memu_item.resources),
            similarity_score=getattr(memu_item, "similarity", None),
            backend_metadata={"memu_id": memu_item.id},
        )

    def _infer_category(self, memory_type: str) -> str:
        """Map memory_type to MemU category name."""
        return {
            "fact": "facts",
            "preference": "preferences",
            "pattern": "patterns",
            "context": "context",
        }.get(memory_type, "general")
```

### Mem0 Backend

```python
# src/gobby/memory/backends/mem0.py

class Mem0MemoryBackend:
    """
    Backend for Mem0 (https://mem0.ai).

    Mem0 provides:
    - Enterprise-grade memory infrastructure
    - Automatic memory extraction and organization
    - Graph-based memory relationships
    - Multi-user/multi-agent support

    Requires: pip install mem0ai
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,      # For self-hosted
        user_id: str = "default",          # Mem0 user scoping
        agent_id: str | None = None,       # Optional agent scoping
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._user_id = user_id
        self._agent_id = agent_id
        self._client = None

    @property
    def capabilities(self) -> MemoryCapability:
        return (
            MemoryCapability.BASIC |
            MemoryCapability.UPDATE |
            MemoryCapability.SEMANTIC_SEARCH |
            MemoryCapability.TAGS |
            MemoryCapability.DEDUPLICATION |
            MemoryCapability.CROSS_REFERENCES
        )

    @property
    def name(self) -> str:
        return "mem0"

    async def initialize(self) -> None:
        try:
            from mem0 import Memory
        except ImportError:
            raise ImportError(
                "Mem0 backend requires mem0ai. Install with: pip install mem0ai"
            )

        config = {}
        if self._api_key:
            config["api_key"] = self._api_key
        if self._base_url:
            config["base_url"] = self._base_url

        self._client = Memory(**config) if config else Memory()

    async def remember(
        self,
        content: str,
        project_id: str | None = None,
        **kwargs,
    ) -> MemoryRecord:
        # Mem0 uses user_id for scoping, we map project_id
        user_id = self._make_user_id(project_id)

        result = self._client.add(
            content,
            user_id=user_id,
            agent_id=self._agent_id,
            metadata={
                "memory_type": kwargs.get("memory_type", "fact"),
                "importance": kwargs.get("importance", 0.5),
                "tags": kwargs.get("tags", []),
                "source_type": kwargs.get("source_type"),
                "source_session_id": kwargs.get("source_session_id"),
                "gobby_project_id": project_id,
            },
        )

        return self._to_record(result, project_id)

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        user_id = self._make_user_id(query.project_id)

        results = self._client.search(
            query.text,
            user_id=user_id,
            agent_id=self._agent_id,
            limit=query.limit,
        )

        records = [self._to_record(r, query.project_id) for r in results]
        return self._apply_filters(records, query)

    async def get_related(
        self,
        memory_id: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        # Mem0 has graph-based relationships
        memory = await self.get(memory_id)
        if not memory:
            return []

        # Use the memory content to find related
        results = self._client.search(
            memory.content,
            limit=limit + 1,  # +1 to exclude self
        )

        return [
            self._to_record(r, memory.project_id)
            for r in results
            if r.id != memory_id
        ][:limit]

    def _make_user_id(self, project_id: str | None) -> str:
        """Map Gobby project_id to Mem0 user_id."""
        if project_id:
            return f"{self._user_id}:{project_id}"
        return self._user_id

    def _to_record(self, mem0_item, project_id: str | None) -> MemoryRecord:
        """Convert Mem0 item to normalized MemoryRecord."""
        metadata = mem0_item.get("metadata", {})
        return MemoryRecord(
            id=mem0_item["id"],
            content=mem0_item["memory"],
            memory_type=metadata.get("memory_type", "fact"),
            importance=metadata.get("importance", 0.5),
            tags=metadata.get("tags", []),
            created_at=mem0_item.get("created_at", ""),
            updated_at=mem0_item.get("updated_at", ""),
            project_id=metadata.get("gobby_project_id", project_id),
            source_type=metadata.get("source_type"),
            source_session_id=metadata.get("source_session_id"),
            similarity_score=mem0_item.get("score"),
            backend_metadata={"mem0_id": mem0_item["id"]},
        )
```

### Null Backend (Testing)

```python
# src/gobby/memory/backends/null.py

class NullMemoryBackend:
    """
    No-op backend for testing or when memory is disabled.

    All operations succeed but store nothing persistently.
    """

    def __init__(self):
        self._memories: dict[str, MemoryRecord] = {}
        self._counter = 0

    @property
    def capabilities(self) -> MemoryCapability:
        return MemoryCapability.BASIC | MemoryCapability.UPDATE

    @property
    def name(self) -> str:
        return "null"

    async def remember(self, content: str, **kwargs) -> MemoryRecord:
        self._counter += 1
        record = MemoryRecord(
            id=f"null-{self._counter}",
            content=content,
            memory_type=kwargs.get("memory_type", "fact"),
            importance=kwargs.get("importance", 0.5),
            tags=kwargs.get("tags", []),
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        self._memories[record.id] = record
        return record

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        # Simple text matching for testing
        results = []
        for record in self._memories.values():
            if query.text and query.text.lower() in record.content.lower():
                results.append(record)
            elif not query.text:
                results.append(record)
        return results[:query.limit]

    async def forget(self, memory_id: str) -> bool:
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    async def get(self, memory_id: str) -> MemoryRecord | None:
        return self._memories.get(memory_id)

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        self._memories.clear()

    async def health_check(self) -> dict:
        return {"healthy": True, "details": {"type": "null", "count": len(self._memories)}}
```

## MemoryManager Facade

The high-level API adapts to backend capabilities:

```python
# src/gobby/memory/manager.py

class MemoryManager:
    """
    High-level memory API that adapts to backend capabilities.

    This is the primary interface for all memory operations.
    It handles capability detection, graceful degradation,
    and multimodal helpers.
    """

    def __init__(self, backend: MemoryBackend):
        self._backend = backend
        self._initialized = False

    @property
    def backend(self) -> MemoryBackend:
        return self._backend

    @property
    def capabilities(self) -> MemoryCapability:
        return self._backend.capabilities

    def has_capability(self, cap: MemoryCapability) -> bool:
        return (self._backend.capabilities & cap) == cap

    async def initialize(self) -> None:
        if not self._initialized:
            await self._backend.initialize()
            self._initialized = True

    async def shutdown(self) -> None:
        if self._initialized:
            await self._backend.shutdown()
            self._initialized = False

    # === Core Operations ===

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        tags: list[str] | None = None,
        project_id: str | None = None,
        **kwargs,
    ) -> MemoryRecord:
        """Store a memory."""
        # Check for duplicates if supported
        if self.has_capability(MemoryCapability.DEDUPLICATION):
            duplicates = await self._backend.find_duplicates(
                content,
                threshold=0.95,
                project_id=project_id,
            )
            if duplicates:
                logger.info(f"Found duplicate memory: {duplicates[0].id}")
                # Update importance if new one is higher
                if importance > duplicates[0].importance:
                    return await self.update(
                        duplicates[0].id,
                        importance=importance,
                    )
                return duplicates[0]

        return await self._backend.remember(
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            project_id=project_id,
            **kwargs,
        )

    async def recall(
        self,
        query: str | MemoryQuery | None = None,
        **kwargs,
    ) -> list[MemoryRecord]:
        """
        Retrieve memories.

        Accepts either a query string or a MemoryQuery object.
        Additional kwargs are merged into the query.
        """
        if query is None:
            query = MemoryQuery(**kwargs)
        elif isinstance(query, str):
            query = MemoryQuery(text=query, **kwargs)
        else:
            # Merge kwargs into existing query
            for key, value in kwargs.items():
                if hasattr(query, key):
                    setattr(query, key, value)

        # Adapt search mode based on capabilities
        if query.search_mode == "auto":
            if self.has_capability(MemoryCapability.HYBRID_SEARCH):
                query.search_mode = "hybrid"
            elif self.has_capability(MemoryCapability.SEMANTIC_SEARCH):
                query.search_mode = "semantic"
            elif self.has_capability(MemoryCapability.KEYWORD_SEARCH):
                query.search_mode = "keyword"
            else:
                query.search_mode = "exact"

        return await self._backend.recall(query)

    async def forget(self, memory_id: str) -> bool:
        """Delete a memory."""
        return await self._backend.forget(memory_id)

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Get a specific memory."""
        return await self._backend.get(memory_id)

    async def update(
        self,
        memory_id: str,
        **kwargs,
    ) -> MemoryRecord | None:
        """Update a memory. Requires UPDATE capability."""
        if not self.has_capability(MemoryCapability.UPDATE):
            raise NotImplementedError(
                f"Backend '{self._backend.name}' does not support updates"
            )
        return await self._backend.update(memory_id, **kwargs)

    # === Multimodal Helpers ===

    async def remember_with_image(
        self,
        content: str,
        image_path: str,
        generate_description: bool = True,
        **kwargs,
    ) -> MemoryRecord:
        """
        Store a memory with an image attachment.

        If backend doesn't support images, stores text only with warning.
        """
        if not self.has_capability(MemoryCapability.IMAGES):
            logger.warning(
                f"Backend '{self._backend.name}' doesn't support images. "
                "Storing text only."
            )
            return await self.remember(content, **kwargs)

        # Generate description for searchability
        description = None
        if generate_description:
            description = await self._generate_image_description(image_path)

        # Detect MIME type
        mime_type = self._detect_mime_type(image_path)

        attachment = MediaAttachment(
            media_type="image",
            mime_type=mime_type,
            reference=image_path,
            storage_mode="file",
            description=description,
        )

        return await self.remember(
            content=content,
            media=[attachment],
            **kwargs,
        )

    async def remember_screenshot(
        self,
        content: str,
        screenshot_data: bytes,
        filename: str = "screenshot.png",
        **kwargs,
    ) -> MemoryRecord:
        """
        Store a memory with a screenshot (e.g., from Playwright).

        Saves the screenshot to resources directory and creates memory.
        """
        if not self.has_capability(MemoryCapability.IMAGES):
            logger.warning(
                f"Backend '{self._backend.name}' doesn't support images. "
                "Storing text only."
            )
            return await self.remember(content, **kwargs)

        # Save screenshot to resources
        resources_dir = Path(self._get_resources_path())
        resources_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        file_path = resources_dir / unique_filename
        file_path.write_bytes(screenshot_data)

        return await self.remember_with_image(
            content=content,
            image_path=str(file_path),
            **kwargs,
        )

    # === Category Operations (MemU-style) ===

    async def categorize(
        self,
        memory_id: str,
        category: str,
    ) -> MemoryRecord | None:
        """Assign memory to category. Requires CATEGORIES capability."""
        if not self.has_capability(MemoryCapability.CATEGORIES):
            raise NotImplementedError(
                f"Backend '{self._backend.name}' doesn't support categories"
            )
        return await self._backend.categorize(memory_id, category)

    async def list_categories(
        self,
        project_id: str | None = None,
    ) -> list[str]:
        """List available categories. Requires CATEGORIES capability."""
        if not self.has_capability(MemoryCapability.CATEGORIES):
            # Fallback: return memory_type values
            return ["fact", "preference", "pattern", "context"]
        return await self._backend.list_categories(project_id)

    # === Sync Operations ===

    async def export_to_markdown(
        self,
        directory: str,
        project_id: str | None = None,
    ) -> int:
        """
        Export memories to markdown files.

        If backend supports SYNC_MARKDOWN, uses native export.
        Otherwise, generates markdown from memories.
        """
        if self.has_capability(MemoryCapability.SYNC_MARKDOWN):
            return await self._backend.export_markdown(directory, project_id)

        # Fallback: generate markdown ourselves
        return await self._generate_markdown_export(directory, project_id)

    async def import_from_markdown(
        self,
        directory: str,
        project_id: str | None = None,
    ) -> tuple[int, int]:
        """
        Import memories from markdown files.

        If backend supports SYNC_MARKDOWN, uses native import.
        Otherwise, parses markdown and creates memories.
        """
        if self.has_capability(MemoryCapability.SYNC_MARKDOWN):
            return await self._backend.import_markdown(directory, project_id)

        # Fallback: parse markdown ourselves
        return await self._parse_markdown_import(directory, project_id)

    # === Private Helpers ===

    async def _generate_image_description(self, image_path: str) -> str:
        """Use LLM to generate searchable description of image."""
        from gobby.llm.service import LLMService

        llm = LLMService()
        description = await llm.describe_image(
            image_path,
            prompt="Describe this image concisely for search indexing. "
                   "Focus on key visual elements, text content, and context.",
        )
        return description

    def _detect_mime_type(self, file_path: str) -> str:
        """Detect MIME type from file extension."""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"

    def _get_resources_path(self) -> str:
        """Get resources directory path from backend config."""
        if hasattr(self._backend, "_resources_path"):
            return self._backend._resources_path
        return ".gobby/resources"
```

## Configuration

```yaml
# ~/.gobby/config.yaml

memory:
  # Backend selection
  backend: sqlite  # sqlite (default), memu, mem0, null, or custom class path

  # Common settings (apply to all backends)
  enabled: true
  auto_extract: true
  injection_limit: 10
  importance_threshold: 0.3

  # Backend-specific configuration
  backends:
    sqlite:
      # Search
      semantic_search_enabled: true
      embedding_provider: openai
      embedding_model: text-embedding-3-small
      tfidf_enabled: true

      # Decay
      decay_enabled: true
      decay_rate: 0.05
      decay_floor: 0.1

      # Multimodal
      images_enabled: true
      resources_path: .gobby/resources

      # Sync
      markdown_sync_enabled: true  # NEW: Enable MemU-style markdown export

    memu:
      mode: embedded  # embedded or server
      server_url: null  # For server mode: http://localhost:9000
      categories_path: .gobby/memory
      resources_path: .gobby/memory/resources
      auto_categorize: true
      llm_retrieval_enabled: true

    mem0:
      api_key: ${MEM0_API_KEY}  # Or set MEM0_API_KEY env var
      base_url: null  # For self-hosted: http://localhost:8080
      user_id: default
      agent_id: null

    # Custom backend example
    custom:
      class: myproject.memory.CustomMemoryBackend
      config:
        whatever: you_need

# Sync settings (separate from backend)
memory_sync:
  enabled: true
  stealth: false  # true = ~/.gobby (private), false = .gobby (git)
  format: jsonl   # jsonl or markdown
  export_debounce: 5.0
```

## Markdown Sync Format

When `memory_sync.format: markdown` or using MemU backend, memories are stored as:

```
.gobby/memory/
├── preferences.md
├── facts.md
├── patterns.md
├── context.md
└── resources/
    ├── screenshot-001.png
    └── diagram-auth-flow.png
```

### Markdown File Format

```markdown
# Preferences

## Always use conventional commits
- **ID:** mm-abc123
- **Importance:** 0.8
- **Tags:** git, workflow
- **Source:** user
- **Created:** 2024-01-15T10:30:00Z

The team uses conventional commit format for all commits.
Prefix with: feat, fix, docs, style, refactor, test, chore

---

## Prefer functional components
- **ID:** mm-def456
- **Importance:** 0.7
- **Tags:** react, code-style
- **Source:** session
- **Created:** 2024-01-16T14:20:00Z

Use functional components with hooks instead of class components.
Exception: Error boundaries still require class components.

---
```

### Memory with Image

```markdown
## Login page error state
- **ID:** mm-ghi789
- **Importance:** 0.9
- **Tags:** ui, errors, authentication
- **Source:** session
- **Created:** 2024-01-17T09:15:00Z
- **Media:** ![Login error](resources/screenshot-001.png)

Screenshot of the login page showing the error state when
credentials are invalid. Note the red border on input fields
and the error message below the submit button.

---
```

## Implementation Phases

### Phase 1: Protocol & SQLite Refactor

**Goal:** Extract protocol, refactor current implementation, maintain 100% compatibility.

**Tasks:**

- [ ] Create `src/gobby/memory/protocol.py` with types and protocol
- [ ] Create `src/gobby/memory/backends/` package
- [ ] Move current implementation to `backends/sqlite.py`
- [ ] Implement `MemoryBackend` protocol on `SqliteMemoryBackend`
- [ ] Update `MemoryManager` to use protocol
- [ ] Add `NullMemoryBackend` for testing
- [ ] Add backend factory function
- [ ] Add config parsing for backend selection
- [ ] All existing tests must pass unchanged

**Files:**

```
src/gobby/memory/
├── protocol.py        # NEW: Types and protocol
├── manager.py         # MODIFIED: Use protocol
├── backends/
│   ├── __init__.py    # NEW: Backend factory
│   ├── sqlite.py      # MOVED: From current implementation
│   └── null.py        # NEW: Testing backend
```

### Phase 2: Multimodal Support (SQLite)

**Goal:** Add image attachment support to SQLite backend.

**Tasks:**

- [ ] Add `media` JSON column to memories table (migration)
- [ ] Implement `MediaAttachment` storage/retrieval in SQLite backend
- [ ] Add `remember_with_image()` helper to MemoryManager
- [ ] Add `remember_screenshot()` helper for Playwright integration
- [ ] Add LLM-based image description generation
- [ ] Add resources directory management
- [ ] Update MCP tools to support media parameter
- [ ] Add tests for multimodal operations

**Migration:**

```sql
ALTER TABLE memories ADD COLUMN media TEXT;  -- JSON array of MediaAttachment
```

### Phase 3: Markdown Sync

**Goal:** Add MemU-style markdown export/import to SQLite backend.

**Tasks:**

- [ ] Implement `export_markdown()` in SQLite backend
- [ ] Implement `import_markdown()` in SQLite backend
- [ ] Add markdown parsing utilities
- [ ] Update `MemorySyncManager` to support markdown format
- [ ] Add `gobby memory export --format markdown` CLI option
- [ ] Add `gobby memory import --format markdown` CLI option
- [ ] Add tests for markdown sync

### Phase 4: MemU Backend

**Goal:** Integrate MemU as an alternative backend.

**Tasks:**

- [ ] Create `backends/memu.py`
- [ ] Implement full `MemoryBackend` protocol
- [ ] Handle MemU-specific features (categories, LLM retrieval)
- [ ] Add configuration for MemU mode (embedded/server)
- [ ] Add dependency handling (optional memu-py)
- [ ] Add integration tests (marked as `@pytest.mark.integration`)
- [ ] Document MemU setup in README

### Phase 5: Mem0 Backend

**Goal:** Integrate Mem0 as an alternative backend.

**Tasks:**

- [ ] Create `backends/mem0.py`
- [ ] Implement `MemoryBackend` protocol
- [ ] Handle Mem0-specific features (graph relationships)
- [ ] Map project_id to Mem0 user_id scoping
- [ ] Add configuration for Mem0 API/self-hosted
- [ ] Add dependency handling (optional mem0ai)
- [ ] Add integration tests
- [ ] Document Mem0 setup in README

### Phase 6: Documentation & Polish

**Tasks:**

- [ ] Update `docs/guides/memory.md` with backend selection
- [ ] Add backend comparison table
- [ ] Add migration guide (SQLite → MemU/Mem0)
- [ ] Add troubleshooting section
- [ ] Performance benchmarks
- [ ] Update CLAUDE.md with new capabilities

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Default backend | SQLite | Zero-config, works out of the box |
| 2 | Protocol style | Python Protocol (structural typing) | No base class inheritance required, backends can be any class |
| 3 | Capability detection | Flag enum | Composable, easy to check multiple capabilities |
| 4 | Image storage | File references | Don't bloat DB with binary data |
| 5 | Markdown format | MemU-compatible | Interoperability, proven design |
| 6 | Backend instantiation | Factory + config | Single source of truth for backend selection |
| 7 | Missing capability handling | Graceful degradation + logging | Don't fail, warn and continue |
| 8 | MemU/Mem0 dependencies | Optional (lazy import) | Don't require unless using that backend |

## Migration from V2

Memory V3 is **additive** to V2. The TF-IDF search, cross-references, and visualization from V2 remain part of the SQLite backend. V3 adds:

1. Backend abstraction (protocol)
2. Multimodal support (images)
3. Markdown sync format
4. External backend integrations (MemU, Mem0)

**V2 features in V3 context:**

- TF-IDF search → SQLite backend capability (`KEYWORD_SEARCH`)
- Cross-references → SQLite backend capability (`CROSS_REFERENCES`)
- Visualization → Utility function, works with any backend

## Future Enhancements

- **Audio memory** - Voice notes, meeting recordings
- **Document memory** - PDF, Word doc content extraction
- **Memory graphs** - Visualization across backends
- **Backend chaining** - Read from Mem0, write to SQLite
- **Memory migration** - Export from one backend, import to another
- **Hybrid backend** - Different backends for different memory types
