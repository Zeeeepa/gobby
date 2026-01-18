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

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| **Root Epic** | #4424 | open |
| **Phase 1: Protocol & SQLite Refactor** | #4425 | open |
| Create protocol.py with memory protocol types | #4431 | open |
| Create backends/__init__.py with factory function | #4432 | open |
| Create backends/null.py for testing | #4433 | open |
| Create backends/sqlite.py refactoring LocalMemoryManager | #4434 | open |
| Add backend config schema to persistence.py | #4435 | open |
| Modify manager.py to use backend protocol pattern | #4436 | open |
| Update existing memory tests for backend pattern | #4437 | open |
| Modify sync/memories.py to become backup-only | #4438 | open |
| Rename MCP tool recall_memory to search_memories | #4439 | open |
| Create slash commands skill file for memory operations | #4440 | open |
| Run full test suite and type check | #4441 | open |
| **Phase 2: Multimodal Support** | #4426 | blocked |
| Add media column migration to memories table | #4442 | open |
| Add describe_image abstract method to LLMProvider base class | #4443 | open |
| Implement describe_image in ClaudeLLMProvider | #4444 | open |
| Implement describe_image in GeminiLLMProvider | #4445 | open |
| Implement describe_image in CodexLLMProvider | #4446 | open |
| Update SqliteMemoryBackend to store/retrieve media attachments | #4447 | open |
| Create .gobby/resources/ directory configuration | #4448 | open |
| Add remember_with_image helper to MemoryManager | #4449 | open |
| Add remember_screenshot helper for browser automation | #4450 | open |
| Add tests for media column migration and Memory dataclass | #4451 | open |
| Add tests for LLMProvider describe_image methods | #4452 | open |
| Add tests for MemoryManager image helpers | #4453 | open |
| **Phase 3: MemU Backend** | #4427 | blocked |
| Create backends/memu.py with MemoryBackend protocol implementation | #4454 | open |
| Implement create_memory mapping to MemUService.memorize() | #4455 | open |
| Implement search_memories mapping to MemUService.retrieve() | #4456 | open |
| Implement remaining MemoryBackend protocol methods | #4457 | open |
| Add MemU configuration to persistence.py | #4458 | open |
| Register MemUBackend in backends factory | #4459 | open |
| Add unit tests for MemUBackend | #4460 | open |
| Update existing config tests for MemU configuration | #4461 | open |
| **Phase 4: Mem0 Backend** | #4428 | blocked |
| Create backends directory structure | #4462 | open |
| Define MemoryBackend protocol in protocol.py | #4463 | open |
| Add Mem0Config to persistence.py | #4464 | open |
| Add mem0 section to config.yaml template | #4465 | open |
| Create Mem0Backend implementation | #4466 | open |
| Add mem0ai as optional dependency | #4467 | open |
| Update backends/__init__.py with factory and exports | #4468 | open |
| Write unit tests for Mem0Backend | #4469 | open |
| Add tests for Mem0Config in test_persistence.py | #4470 | open |
| **Phase 5: OpenMemory Backend** | #4429 | blocked |
| Add OpenMemory base_url configuration to persistence.py | #4471 | open |
| Create backends/openmemory.py with MemoryBackend protocol implementation | #4472 | open |
| Implement REST API endpoint connections in OpenMemoryBackend | #4473 | open |
| Add health_check method to OpenMemoryBackend | #4474 | open |
| Register OpenMemoryBackend in backends factory | #4475 | open |
| Add unit tests for OpenMemoryBackend | #4476 | open |
| Update existing config tests for OpenMemory configuration | #4477 | open |
| **Phase 6: Markdown Export** | #4430 | blocked |
| Add export_markdown() method to MemoryManager | #4478 | open |
| Add unit tests for export_markdown() method | #4479 | open |
| Add export command to memory CLI | #4480 | open |
| Add CLI tests for memory export command | #4481 | open |
| Create markdown export format documentation | #4482 | open |
