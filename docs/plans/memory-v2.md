# Memory v2: Cloud-Ready Memory Architecture

## Overview

Memory v2 evolves Gobby's memory system from local-only SQLite to a **pluggable backend architecture** that supports local storage, cloud services, and graceful degradation between them. This enables Gobby Pro's cloud memory features while maintaining a fully functional free tier.

## Vision

> "Your agent's memory should survive anything—compactions, crashes, even closed terminals."

Current memory (v1) works well for local single-machine usage, but has limitations:

1. **No semantic graph** - Memories are flat, no relationships between concepts
2. **No temporal awareness** - Can't answer "what did I learn last week?"
3. **Lost on ungraceful exit** - Terminal close = lost final segment memories
4. **No cross-device sync** - Memories stuck on one machine

Memory v2 addresses these through:

1. **Backend abstraction** - Swap storage implementations without changing API
2. **Cloud backend option** - Vector + graph database for semantic search
3. **Daemon-based recovery** - Never lose memories, even on crash
4. **Graceful degradation** - Falls back through layers when services unavailable

## Architecture

### Backend Protocol

```python
class MemoryBackend(Protocol):
    """Protocol for swappable memory backends."""

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        tags: list[str] | None = None,
        supersedes: str | None = None,
    ) -> Memory: ...

    async def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
        use_semantic: bool = True,
    ) -> list[Memory]: ...

    async def forget(self, memory_id: str) -> bool: ...

    async def correct(
        self,
        memory_id: str,
        new_content: str,
        reason: str = "user_correction"
    ) -> Memory: ...

    async def save_conversation_segment(
        self,
        session_id: str,
        messages: list[dict],
        extract_memories: bool = True,
    ) -> dict: ...

    def is_available(self) -> bool: ...
```

### Backend Implementations

| Backend | Storage | Semantic Search | Relationships | Use Case |
|---------|---------|-----------------|---------------|----------|
| `SQLiteBackend` | Local SQLite | OpenAI embeddings (optional) | None | Free tier, offline |
| `CloudBackend` | Vector DB + Graph DB | Native | Full graph | Gobby Pro |

### Graceful Degradation Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: Cloud Backend (Primary when available)                    │
│  ─────────────────────────────────────────────────────────────────  │
│  Vector DB (semantic) + Graph DB (relationships) + LLM extraction   │
│  Features: Semantic search, temporal queries, cross-session graph   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ (if cloud unavailable)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2: SQLite + Embeddings (Fallback)                            │
│  ─────────────────────────────────────────────────────────────────  │
│  Local SQLite + optional OpenAI embeddings                          │
│  Features: Semantic search (if API key), text search fallback       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ (if database unavailable)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: JSONL Files (Last resort)                                 │
│  ─────────────────────────────────────────────────────────────────  │
│  .gobby/memories.jsonl - Git-tracked, human-readable                │
│  Features: Text search only, but always works                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ (always available)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 4: Session Summaries (Human backup)                          │
│  ─────────────────────────────────────────────────────────────────  │
│  compact_markdown / summary_markdown in sessions table              │
│  Features: Re-parseable, audit trail, zero dependencies             │
└─────────────────────────────────────────────────────────────────────┘
```

## Memory Types

### Type 1: Auto-Extracted Memories

Source: LLM analysis of conversation segments
When: PRE_COMPACT, SESSION_END, recovery job

```
Examples:
  - "Project uses pytest with fixtures in conftest.py"
  - "JWT tokens use RS256 algorithm"
  - "User asked for dark mode during task gt-015"

Properties:
  - Temporal: Connected to sessions, tasks, timestamps
  - Medium importance (0.5-0.7)
  - May decay over time if not accessed
```

### Type 2: Explicit Facts (User-provided)

Source: User explicitly says "remember this" or uses gobby-memory.remember
When: Any time during session

```
Examples:
  - "Remember: always use yarn, not npm in this project"
  - "Remember: Josh prefers functional components"
  - "Remember: deploy to staging before prod"

Properties:
  - HIGH importance (0.8-1.0)
  - Never decays
  - Surfaced prominently in recall
```

### Type 3: Corrections (Override previous memories)

Source: User corrects a fact or preference
When: Any time, usually after seeing incorrect recall

```
Examples:
  - "Actually the rate limit is 500/min, not 1000"
  - "I changed my mind - use npm, not yarn"

Storage Strategy:
  - Create SUPERSEDES relationship to old memory
  - Old memory marked as deprecated but retained for audit
  - Only latest version returned in recall
```

### Type 4: Project Context (from codebase scan)

Source: init_memory scan of codebase and CLAUDE.md
When: First session in project, or explicit refresh

```
Examples:
  - "Project uses FastAPI with Pydantic models"
  - "Test command is 'uv run pytest'"
  - "Main entry point is src/cli.py"

Properties:
  - Medium importance (0.6)
  - Tagged as source="codebase_scan"
  - Can be refreshed on demand
```

## Recovery Architecture

### Data Available in Daemon

The daemon already stores session messages in real-time:

```sql
-- session_messages table (populated by SessionMessageProcessor every 2s)
session_id | message_index | role | content | tool_name | tool_input | ...

-- session_message_state table (tracks processing progress)
session_id | last_byte_offset | last_message_index | last_processed_at
```

This means **all conversation data is already captured**, even if SESSION_END hook never fires.

### Recovery Flow for Ungraceful Exits

```
T+0        User closes terminal (SIGKILL, no SESSION_END)
T+2s       SessionMessageProcessor stores final messages (already running)
T+30min    SessionLifecycleManager.expire_stale_sessions() marks as "paused"
T+35min    SessionLifecycleManager.process_pending_transcripts() runs
T+35min    NEW: _extract_memories_for_session() recovers to memory backend

RESULT: Maximum 30-40 minute delay, but NO MEMORY LOSS
```

### New Column for Tracking

```sql
-- Add to sessions table
ALTER TABLE sessions ADD COLUMN memory_sync_index INTEGER DEFAULT 0;
-- Tracks last message_index synced to memory backend
```

## Session Lifecycle Integration

### Memory Save Points

| Event | Action | Data Saved |
|-------|--------|------------|
| SESSION_START | `memory_sync_import` | Load from .gobby/memories.jsonl |
| BEFORE_AGENT | `memory_recall_for_prompt` | Inject relevant memories |
| PRE_COMPACT | `save_conversation_segment` | **CRITICAL**: Save segment before compaction |
| SESSION_END (graceful) | `save_conversation_segment` + `memory_extract` | Final segment + LLM extraction |
| Session recovery (daemon) | `recover_memories_from_messages` | Parse session_messages table |

### Workflow Actions

```yaml
# session-lifecycle.yaml (enhanced)

triggers:
  on_session_start:
    - action: memory_sync_import
    - action: memory_recall_context
      when: "backend.is_available()"
      fallback_action: memory_recall_relevant

  on_before_agent:
    - action: memory_recall_for_prompt
      limit: 5

  on_pre_compact:
    # CRITICAL: Save segment BEFORE context is cleared
    - action: memory_save_segment
      include_messages_since: "session.memory_sync_index"
    - action: generate_handoff
      mode: compact

  on_session_end:
    - action: memory_save_segment
      final: true
    - action: memory_extract
    - action: memory_sync_export
```

## MCP Tools

### Enhanced Memory Tools

```python
@registry.tool(name="remember_fact")
async def remember_fact(
    content: str,
    importance: float = 0.9,
    tags: list[str] | None = None,
    supersedes: str | None = None,
) -> dict:
    """Store an explicit fact with high importance."""

@registry.tool(name="correct_memory")
async def correct_memory(
    query: str,
    new_content: str,
) -> dict:
    """Find and correct a memory."""

@registry.tool(name="recall_temporal")
async def recall_temporal(
    query: str,
    since: str | None = None,  # "yesterday", "last week", ISO date
    until: str | None = None,
) -> dict:
    """Recall memories with temporal filtering (cloud backend only)."""
```

## Configuration

```yaml
# ~/.gobby/config.yaml

memory:
  enabled: true
  backend: "sqlite"  # "sqlite" | "cloud"

  # Cloud backend settings (Gobby Pro)
  cloud:
    api_url: "https://api.gobby.dev/v1"
    api_key: "${GOBBY_PRO_KEY}"
    timeout: 10.0
    retry_count: 3

  # Existing settings
  auto_extract: true
  injection_limit: 10
  importance_threshold: 0.3

  # Recovery settings
  recovery:
    enabled: true
    check_interval_minutes: 10
    stale_session_timeout_minutes: 30
```

## Gobby Pro Features

Cloud backend enables premium features:

| Feature | Free (SQLite) | Pro (Cloud) |
|---------|---------------|-------------|
| Memory storage | Local only | Cloud + local backup |
| Semantic search | Optional (needs OpenAI key) | Native |
| Temporal queries | No | Yes |
| Memory relationships | No | Graph-based |
| Cross-device sync | No | Yes |
| Team memories | No | Yes |
| Crash recovery | 30-40 min delay | Near real-time |

## Implementation Phases

### Phase 1: Protocol & Refactor (Pre-launch)

See [memory-v2-protocol.md](./memory-v2-protocol.md) for detailed implementation plan.

- Define `MemoryBackend` protocol
- Refactor `MemoryManager` to implement protocol as `SQLiteBackend`
- Add config schema for backend selection
- Add `memory_sync_index` column to sessions table

**Estimated effort: 6-10 hours**

### Phase 2: Cloud Backend (Post-MVP)

- Implement `CloudBackend` adapter
- Deploy cloud infrastructure (Vector DB + Graph DB)
- Integrate with billing system
- Add `gobby pro` CLI commands

**Estimated effort: 2-3 weeks**

### Phase 3: Recovery Enhancement (Post-MVP)

- Add `_extract_memories_for_session()` to `SessionLifecycleManager`
- Implement segment-based memory extraction
- Add memory deduplication across segments

**Estimated effort: 1 week**

### Phase 4: Corrections & Versioning (Post-MVP)

- Implement memory correction workflow
- Add `SUPERSEDES` relationship tracking
- Build memory version history

**Estimated effort: 1 week**

### Phase 5: Team Features (Future)

- Shared team memory namespace
- Memory access controls
- Organizational knowledge aggregation

**Estimated effort: 2-3 weeks**

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | **Backend selection** | Config-driven, runtime switchable | Allows upgrade without migration |
| 2 | **Recovery timing** | Use existing SessionLifecycleManager | Infrastructure already exists |
| 3 | **Correction model** | SUPERSEDES relationship | Preserves audit trail |
| 4 | **Cloud vs local** | Both, with fallback | Best UX for all users |
| 5 | **Segment boundaries** | PRE_COMPACT events | Natural save points |
| 6 | **Keep summary_markdown?** | Yes, as backup layer | Human-readable fallback |

## References

- [Memory v1 Plan](./completed/MEMORY.md) - Original memory implementation
- [Session Lifecycle](../src/gobby/sessions/lifecycle.py) - Recovery infrastructure
- [Session Messages](../src/gobby/storage/session_messages.py) - Real-time message capture
