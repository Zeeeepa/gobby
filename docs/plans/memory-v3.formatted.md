# Memory System V3

## Phase 1: Protocol & SQLite Refactor

**Goal**: Extract protocol, refactor current implementation, maintain 100% compatibility.

**Tasks:**
- [ ] Create `protocol.py` with types (MemoryCapability, MemoryQuery, MediaAttachment, MemoryRecord, MemoryBackend)
- [ ] Create `backends/__init__.py` with factory
- [ ] Create `backends/sqlite.py` (refactor LocalMemoryManager)
- [ ] Create `backends/null.py`
- [ ] Modify `manager.py` to use backend protocol
- [ ] Modify `sync/memories.py` → backup-only
- [ ] Add config for backend selection
- [ ] Rename MCP tool `recall_memory` → `search_memories`
- [ ] Create slash commands (`/gobby:remember`, `/gobby:recall`, `/gobby:forget`)
- [ ] Ensure all existing tests pass

## Phase 2: Multimodal Support

**Goal**: Add image attachment support with LLM-generated descriptions.

**Tasks:**
- [ ] Add `MediaAttachment` to protocol
- [ ] Add `media` column migration
- [ ] Add `LLMService.describe_image()`
- [ ] Add `remember_with_image()`, `remember_screenshot()` helpers
- [ ] Update SqliteMemoryBackend for media
- [ ] Add `.gobby/resources/` directory
- [ ] Add tests

## Phase 3: MemU Backend

**Goal**: Integrate MemU framework as pluggable backend option.

**Tasks:**
- [ ] Create `backends/memu.py`
- [ ] Map to MemUService API (`memorize()`, `retrieve()`)
- [ ] Add integration tests

## Phase 4: Mem0 Backend

**Goal**: Integrate Mem0 cloud API as pluggable backend option.

**Tasks:**
- [ ] Create `backends/mem0.py`
- [ ] Map to Memory API (`add()`, `search()`)
- [ ] Add integration tests

## Phase 5: OpenMemory Backend

**Goal**: Integrate self-hosted OpenMemory as pluggable backend option.

**Tasks:**
- [ ] Create `backends/openmemory.py`
- [ ] Connect to REST API
- [ ] Add health checks
- [ ] Add integration tests

## Phase 6: Markdown Sync (Optional)

**Goal**: Add markdown export capability for memory portability.

**Tasks:**
- [ ] Add `export_markdown()` method
- [ ] Create markdown format
- [ ] Add CLI commands