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

| Spec Item | Task Ref | Status |
|-----------|----------|--------|
| **Epic: Memory V3** | #4300 | open |
| **Phase 1: Protocol & SQLite Refactor** | #4301 | open |
| Create protocol.py | #4307 | open |
| Create backends/__init__.py | #4308 | open |
| Create backends/sqlite.py | #4309 | open |
| Create backends/null.py | #4310 | open |
| Modify manager.py | #4311 | open |
| Modify sync/memories.py | #4312 | open |
| Add config schema | #4313 | open |
| Rename recall_memory | #4314 | open |
| Create slash commands | #4315 | open |
| **Phase 2: Multimodal Support** | #4302 | open |
| Add media column migration | #4316 | open |
| Add LLMService.describe_image() | #4317 | open |
| Add remember_with_image() | #4318 | open |
| Add remember_screenshot() | #4319 | open |
| Update SqliteMemoryBackend for media | #4320 | open |
| Create .gobby/resources/ | #4321 | open |
| **Phase 3: MemU Backend** | #4303 | open |
| Create backends/memu.py | #4322 | open |
| Map MemUService.memorize() | #4323 | open |
| Map MemUService.retrieve() | #4324 | open |
| **Phase 4: Mem0 Backend** | #4304 | open |
| Create backends/mem0.py | #4325 | open |
| Map Memory.add() | #4326 | open |
| Map Memory.search() | #4327 | open |
| Add API key config | #4328 | open |
| **Phase 5: OpenMemory Backend** | #4305 | open |
| Create backends/openmemory.py | #4329 | open |
| Connect to REST API | #4330 | open |
| Add health check | #4331 | open |
| Add base_url config | #4332 | open |
| **Phase 6: Markdown Export** | #4306 | open |
| Add export_markdown() | #4333 | open |
| Create markdown format spec | #4334 | open |
| Add CLI command | #4335 | open |
