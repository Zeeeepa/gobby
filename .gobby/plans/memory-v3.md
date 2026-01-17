# Memory V3: Backend Abstraction Layer

## Overview

Transform gobby-memory from a monolithic implementation into a **pluggable abstraction layer** that integrates with external memory systems. Users can choose between Gobby's built-in SQLite backend or plug in established memory frameworks like MemU, Mem0, or OpenMemory.

**Strategic rationale:** Reducing switching costs accelerates adoption. Users invested in Mem0 or MemU can use Gobby's orchestration layer without migrating memory infrastructure.

**Detailed architecture:** See `docs/plans/memory-v3.md` for complete protocol definitions, backend implementations, and configuration details.

## Constraints

- Maintain 100% backward compatibility with existing MCP tool interface
- Zero external dependencies for SQLite backend (built-in)
- All backends get universal JSONL backup automatically
- Graceful degradation for backends with fewer capabilities

## Phase 1: Protocol & SQLite Refactor

**Goal**: Extract protocol, refactor current implementation into backend pattern, maintain full compatibility.

**Tasks:**
- [ ] Create `protocol.py` with MemoryCapability, MemoryQuery, MediaAttachment, MemoryRecord types (category: code)
- [ ] Create `backends/__init__.py` with backend factory function (category: code)
- [ ] Create `backends/sqlite.py` refactoring LocalMemoryManager into SqliteMemoryBackend (category: code)
- [ ] Create `backends/null.py` for testing (category: code)
- [ ] Modify `manager.py` to use backend protocol pattern (category: code)
- [ ] Modify `sync/memories.py` to become backup-only (category: code)
- [ ] Add config schema for backend selection in config.yaml (category: config)
- [ ] Rename MCP tool `recall_memory` to `search_memories` (category: code)
- [ ] Create slash commands `/gobby:remember`, `/gobby:recall`, `/gobby:forget` (category: code)

## Phase 2: Multimodal Support

**Goal**: Add image attachment support with LLM-generated descriptions for browser automation use cases.

**Tasks:**
- [ ] Add `media` column migration to memories table (category: code, depends: Phase 1)
- [ ] Add `LLMService.describe_image()` method (category: code)
- [ ] Add `remember_with_image()` helper in MemoryManager (category: code, depends: LLMService.describe_image)
- [ ] Add `remember_screenshot()` helper for Playwright/Puppeteer (category: code, depends: remember_with_image)
- [ ] Update SqliteMemoryBackend to store/retrieve media attachments (category: code)
- [ ] Create `.gobby/resources/` directory for local image storage (category: config)

## Phase 3: MemU Backend

**Goal**: Add integration with MemU framework for users who prefer markdown-based memory.

**Tasks:**
- [ ] Create `backends/memu.py` implementing MemoryBackend protocol (category: code, depends: Phase 1)
- [ ] Map MemUService.memorize() to create_memory (category: code)
- [ ] Map MemUService.retrieve() to search_memories (category: code)

## Phase 4: Mem0 Backend

**Goal**: Add integration with Mem0 cloud API for users who prefer managed memory.

**Tasks:**
- [ ] Create `backends/mem0.py` implementing MemoryBackend protocol (category: code, depends: Phase 1)
- [ ] Map Memory.add() to create_memory (category: code)
- [ ] Map Memory.search() to search_memories (category: code)
- [ ] Add API key configuration to config.yaml (category: config)

## Phase 5: OpenMemory Backend

**Goal**: Add integration with self-hosted OpenMemory for users who want local embedding-based memory.

**Tasks:**
- [ ] Create `backends/openmemory.py` implementing MemoryBackend protocol (category: code, depends: Phase 1)
- [ ] Connect to REST API endpoints (category: code)
- [ ] Add health check implementation (category: code)
- [ ] Add base_url configuration to config.yaml (category: config)

## Phase 6: Markdown Export (Optional)

**Goal**: Add human-readable markdown export for memory browsing and debugging.

**Tasks:**
- [ ] Add `export_markdown()` method to MemoryManager (category: code)
- [ ] Create markdown format spec (single file vs directory) (category: document)
- [ ] Add `gobby memory export --format markdown` CLI command (category: code)

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
