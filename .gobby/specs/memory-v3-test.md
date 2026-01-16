# Memory V3: Backend Abstraction Layer

## Overview

Transform gobby-memory from a monolithic implementation into a pluggable abstraction layer that integrates with external memory systems. Users can choose between Gobby's built-in SQLite backend or plug in established memory frameworks like MemU, Mem0, or OpenMemory.

**Strategic rationale:** Reducing switching costs accelerates adoption. Users already invested in Mem0 or MemU can use Gobby's orchestration layer without migrating their memory infrastructure.

**What stays the same:**
- MCP tool interface (`create_memory`, `search_memories`, `delete_memory`, etc.)
- Workflow integration and hooks
- Session linking and project scoping
- CLI commands

## Constraints

- Zero breaking changes to existing MCP tool interface
- SQLite backend must retain all V2 features (TF-IDF, cross-references, decay)
- External backends are optional dependencies (lazy-loaded)
- JSONL backup works universally across all backends
- Image descriptions route through LLMService (provider-agnostic)

## Phase 1: Protocol & SQLite Refactor

**Goal**: Extract protocol, refactor current implementation into backend pattern, maintain 100% compatibility.

**Tasks:**
- [ ] Create memory protocol types in `src/gobby/memory/protocol.py` (MemoryCapability, MemoryQuery, MediaAttachment, MemoryRecord, MemoryBackend)
- [ ] Create backends package with factory in `src/gobby/memory/backends/__init__.py`
- [ ] Create SqliteMemoryBackend in `src/gobby/memory/backends/sqlite.py` (refactor from LocalMemoryManager)
- [ ] Create NullMemoryBackend in `src/gobby/memory/backends/null.py`
- [ ] Update MemoryManager facade to use backend protocol
- [ ] Update MemoryBackupManager to trigger on facade operations
- [ ] Add backend selection to DaemonConfig schema
- [ ] Rename MCP tool `recall_memory` to `search_memories`

## Phase 2: Multimodal Support

**Goal**: Add image attachment support with LLM-generated descriptions for browser automation use cases.

**Tasks:**
- [ ] Create database migration for media column in memories table
- [ ] Add `describe_image()` method to LLMService
- [ ] Add `remember_with_image()` and `remember_screenshot()` helpers to MemoryManager
- [ ] Update SqliteMemoryBackend to store and retrieve media attachments
- [ ] Create `.gobby/resources/` directory management utility
- [ ] Add `create_memory_with_image` MCP tool

## Phase 3: MemU Backend

**Goal**: Integrate with MemU framework for users who prefer markdown-based memory.

**Tasks:**
- [ ] Create MemuMemoryBackend in `src/gobby/memory/backends/memu.py`
- [ ] Map operations to MemU API (`memorize()`, `retrieve()`)
- [ ] Handle MemU category mapping to MemoryRecord
- [ ] Add memu backend config section and optional `memu-py` dependency

## Phase 4: Mem0 Backend

**Goal**: Integrate with Mem0 cloud API for users with existing Mem0 infrastructure.

**Tasks:**
- [ ] Create Mem0MemoryBackend in `src/gobby/memory/backends/mem0.py`
- [ ] Map operations to Mem0 API (`add()`, `search()`)
- [ ] Handle Mem0 metadata mapping to MemoryRecord
- [ ] Add mem0 backend config section with API key support and optional `mem0ai` dependency

## Phase 5: OpenMemory Backend

**Goal**: Integrate with self-hosted OpenMemory for users wanting local semantic memory.

**Tasks:**
- [ ] Create OpenMemoryBackend in `src/gobby/memory/backends/openmemory.py`
- [ ] Implement REST API client for OpenMemory endpoints
- [ ] Add health check for OpenMemory connectivity
- [ ] Add openmemory backend config section

## Phase 6: Markdown Export (Optional)

**Goal**: Export memories to human-readable markdown for documentation purposes.

**Tasks:**
- [ ] Add `export_markdown()` method to MemoryManager
- [ ] Create markdown format template
- [ ] Add `gobby memory export --format markdown` CLI command

## Phase 7: Slash Commands (Optional)

**Goal**: Add friendly slash command aliases for common memory operations.

**Tasks:**
- [ ] Create `/gobby:remember` skill (wraps `create_memory`)
- [ ] Create `/gobby:recall` skill (wraps `search_memories`)
- [ ] Create `/gobby:forget` skill (wraps `delete_memory`)

---

## Architecture Reference

```
┌───────────────────────────────────────────────────────────────────────┐
│                       MemoryManager (facade)                          │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ create_memory(content, ...)                                     │  │
│  │   1. backend.create_memory() → primary storage                  │  │
│  │   2. backup_manager.trigger_export() → .gobby/memories.jsonl    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
                               │
      ┌─────────────┬──────────┼───────────┬─────────────┐
      │             │          │           │             │
 ┌────▼────┐  ┌─────▼─────┐ ┌──▼───┐ ┌─────▼──────┐ ┌────▼────┐
 │ SQLite  │  │   MemU    │ │ Mem0 │ │ OpenMemory │ │ Custom  │
 │ Backend │  │  Backend  │ │Backend│ │  Backend   │ │ Backend │
 └─────────┘  └───────────┘ └──────┘ └────────────┘ └─────────┘
```

## Key Protocol Types

```python
class MemoryCapability(Flag):
    BASIC = auto()              # create, search, delete, get
    UPDATE = auto()             # update existing memories
    SEMANTIC_SEARCH = auto()    # Embedding-based search
    KEYWORD_SEARCH = auto()     # BM25/TF-IDF search
    IMAGES = auto()             # Image attachments
    CATEGORIES = auto()         # Hierarchical organization
    TAGS = auto()               # Tag-based filtering
    IMPORTANCE_DECAY = auto()   # Auto importance decay

@dataclass
class MemoryRecord:
    id: str
    content: str
    memory_type: str                    # fact, preference, pattern, context
    importance: float                   # 0.0-1.0
    tags: list[str]
    created_at: str
    updated_at: str
    project_id: str | None
    media: list[MediaAttachment]        # Image attachments
    similarity_score: float | None      # From search results

@runtime_checkable
class MemoryBackend(Protocol):
    @property
    def capabilities(self) -> MemoryCapability: ...
    async def create_memory(...) -> MemoryRecord: ...
    async def search_memories(query: MemoryQuery) -> list[MemoryRecord]: ...
    async def delete_memory(memory_id: str) -> bool: ...
    async def get_memory(memory_id: str) -> MemoryRecord | None: ...
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| JSONL sync | Universal backup at facade level | All backends get backup; migration path |
| JSONL mode | Snapshot (periodic rewrite) | Simpler than append-only |
| Search abstraction | Delegate to backend's native search | SQLite→TF-IDF, MemU→RAG, Mem0→embedding |
| Image descriptions | Route through LLMService | Provider-agnostic |

## Configuration Example

```yaml
memory:
  backend: sqlite  # sqlite, memu, mem0, openmemory, null
  enabled: true
  importance_threshold: 0.3

  backends:
    sqlite:
      tfidf_enabled: true
      decay_enabled: true
      images_enabled: true

    mem0:
      api_key: ${MEM0_API_KEY}

    openmemory:
      base_url: http://localhost:8765
```

## Task Mapping

<!-- Updated after task creation -->
| Spec Item | Task Ref | Status |
|-----------|----------|--------|
| Phase 1: Protocol & SQLite Refactor | | |
| Phase 2: Multimodal Support | | |
| Phase 3: MemU Backend | | |
| Phase 4: Mem0 Backend | | |
| Phase 5: OpenMemory Backend | | |
| Phase 6: Markdown Export | | |
| Phase 7: Slash Commands | | |
