# Memory v4: Extraction Research & Improvement Plan

Research into how open-source AI memory platforms extract memories from session
transcripts, compared to Gobby's current approach, with concrete improvement
recommendations.

**Date**: 2026-02-05
**Status**: Research complete, implementation pending

---

## Part 1: How Gobby Currently Extracts Memories

Gobby has **two extraction mechanisms**, but only one is active:

### 1. Agent-Driven Proactive Capture (ACTIVE)

- `proactive-memory` skill (`alwaysApply: true`) instructs agents to call `create_memory` during work
- Relies entirely on the agent noticing something valuable and choosing to save it
- Uses the "5-minute rule" heuristic
- **Problem**: Agents rarely do this unprompted. Memory quality depends on the model's multitasking ability while it's focused on the actual coding task

**Key files:**

- `src/gobby/install/shared/skills/proactive-memory/SKILL.md`

### 2. Batch LLM Extraction (AVAILABLE BUT DISABLED)

- `SessionMemoryExtractor` in `src/gobby/memory/extractor.py`
- Prompt at `src/gobby/install/shared/prompts/memory/extract.md`
- Was removed from `session-lifecycle.yaml` `on_session_end` (lines 222-224 explicitly comment it out)
- Pipeline: load last 50 turns -> render prompt -> single LLM call -> parse JSON -> Jaccard dedup -> store
- **Problems**:
  - Only sees last 50 turns (misses early session context)
  - No existing memories passed to LLM for dedup (only checks `content_exists` post-extraction)
  - Single LLM call with no update/conflict resolution
  - No rolling summary or context compression for long sessions

**Key files:**

- `src/gobby/memory/extractor.py` -- `SessionMemoryExtractor`
- `src/gobby/install/shared/prompts/memory/extract.md` -- extraction prompt
- `src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml` -- lifecycle triggers
- `src/gobby/workflows/memory_actions.py` -- `handle_memory_extract` action handler

### 3. Background Transcript Processor (NO MEMORY EXTRACTION)

- `SessionLifecycleManager._process_pending_transcripts()` in `src/gobby/sessions/lifecycle.py`
- Processes expired sessions: parses JSONL, stores messages, aggregates token usage
- Does NOT extract memories -- purely for transcript archival and cost tracking

**Key files:**

- `src/gobby/sessions/lifecycle.py` -- `SessionLifecycleManager`
- `src/gobby/sync/memories.py` -- JSONL export/import (`MemoryBackupManager`)

---

## Part 2: Industry Research -- How Other Platforms Extract Memories

### Mem0 (github.com/mem0ai/mem0)

#### Architecture: Two-Phase Extract-Then-Update Pipeline

Runs on every message pair (incremental, not batch).

**Phase 1 -- Extraction.** The LLM receives three context sources:

1. **Rolling summary** -- condensed summary of the conversation so far
2. **Recent messages** -- last 10 messages
3. **Latest exchange** -- current user/assistant pair

The extraction prompt (`FACT_RETRIEVAL_PROMPT`) instructs the LLM to act as a
"Personal Information Organizer" extracting facts across 7 categories:
personal preferences, important details, plans/intentions, activity preferences,
health/wellness, professional details, miscellaneous.

Key constraint: **"Facts should be GENERATED SOLELY BASED ON THE USER'S
MESSAGES. DO NOT INCLUDE INFORMATION FROM ASSISTANT OR SYSTEM MESSAGES."**

Output: `{"facts": ["fact1", "fact2", ...]}`

**Phase 2 -- Update Decision.** For each extracted fact:

1. Generate an embedding
2. Search vector store for top-5 most similar existing memories
3. Map existing memory UUIDs to temporary string indices (prevents LLM hallucinating IDs)
4. LLM decides one of four actions:

| Decision   | When Used                   | Behavior                              |
| :--------- | :-------------------------- | :------------------------------------ |
| **ADD**    | Entirely new fact           | Generate new ID, store with embedding |
| **UPDATE** | Augments/replaces existing  | Keep original ID, replace text        |
| **DELETE** | Contradicts existing        | Remove from vector store              |
| **NONE**   | Already exists / irrelevant | No change                             |

Output: `{"memory": [{"id": "...", "text": "...", "event": "ADD/UPDATE/DELETE/NONE", "old_memory": "..."}]}`

**Graph Memory Variant (Mem0^g):** Entity extraction -> relationship triplet
generation -> embedding-based graph dedup -> conflict detection against existing
edges. Uses Neo4j.

**Custom Prompts:** Supports `custom_fact_extraction_prompt` for domain-specific
extraction. Best practice: include few-shot examples of positive and negative cases.

### Letta / MemGPT (github.com/letta-ai/letta)

#### Architecture: Agent-Driven Self-Editing Memory

No separate extraction pipeline. The agent itself decides what to remember using
memory-editing tools as part of its normal conversation loop.

**Memory Structure:**

| Layer               | Storage             | Capacity         | Access            |
| :------------------ | :------------------ | :--------------- | :---------------- |
| **Core Memory**     | System prompt area  | 2K chars/section | Always visible    |
| **Archival Memory** | Vector DB table     | Unlimited        | Tool-based search |
| **Recall Memory**   | Conversation log DB | Unlimited        | Date/text search  |

**Memory Editing Tools:**

- `core_memory_append(section, content)` -- add to a memory section
- `core_memory_replace(section, old_str, new_str)` -- edit in-place
- `archival_memory_insert(content)` -- persist to long-term vector store
- `archival_memory_search(query)` -- retrieve from long-term store
- `memory_rethink(section)` -- reorganize/compress a memory section

The system prompt instructs the agent to actively maintain its core memory
sections as a "scratchpad." The agent decides on EVERY turn whether to call
memory tools. Zero extra LLM calls, but quality depends entirely on the model's
multitasking ability.

**Key insight:** Memory is always in-context, so the agent sees what it already
knows and can update/replace. This is what Gobby's `proactive-memory` skill
tries to be, but without the in-context visibility.

### Zep / Graphiti (github.com/getzep/graphiti)

#### Architecture: Multi-Step Temporal Knowledge Graph Pipeline

Most sophisticated extraction, with 4-8 LLM calls per episode and full
bi-temporal tracking.

**Pipeline Steps (per episode):**

1. **Entity Extraction** -- Process current message + 4 previous. Extract
   entities, concepts, actors. Uses a reflexion step where LLM reviews its own
   extraction.

2. **Entity Resolution** -- Embed each entity -> cosine similarity + full-text
   search against existing graph -> LLM compares for duplicates -> merge if found.

3. **Fact/Edge Extraction** -- Extract relationships between identified entities.
   Each edge gets: `relation_type` (SCREAMING_SNAKE_CASE), `fact` (natural language),
   temporal bounds (`valid_at`, `invalid_at`).

4. **Edge Deduplication** -- Hybrid search constrained to edges between same
   entity pairs. LLM determines if new edge duplicates existing.

5. **Temporal Conflict Resolution** -- When new edges contradict existing:
   set old edge's `t_invalid` to new edge's `t_valid`. New information always wins.
   Complete historical record preserved.

6. **Community Detection** -- Label propagation assigns entities to communities.
   Summaries updated incrementally.

**Bi-Temporal Model:** Every edge tracks four timestamps:

- `t'_created`, `t'_expired` -- system/transaction timestamps
- `t_valid`, `t_invalid` -- actual event validity range

Overkill for Gobby's use case, but temporal invalidation is a great idea.

### LangMem (github.com/langchain-ai/langmem)

#### Architecture: Three Memory Types with Parallel Tool Calling

Three cognitive categories:

- **Semantic Memory** -- Facts, preferences, relationships (collections or profiles)
- **Episodic Memory** -- `Episode(observation, thoughts, action, result)` capturing reasoning chains
- **Procedural Memory** -- Behavioral rules, system instructions that evolve

**Extraction via `create_memory_manager`:**

```python
manager = create_memory_manager(
    model="gpt-4o",
    schemas=[Triple],
    instructions="Extract all noteworthy facts, events, and relationships",
    enable_inserts=True,
    enable_updates=True,
    enable_deletes=False,
)
result = manager.invoke({
    "messages": conversation,
    "existing": current_memories  # For dedup/conflict resolution
})
```

Single LLM call uses parallel tool calls to insert/update/delete. All operations
happen atomically. Two timing modes:

| Mode                        | When                | Trade-off                 |
| :-------------------------- | :------------------ | :------------------------ |
| **Conscious (active)**      | During conversation | Immediate, adds latency   |
| **Subconscious (background)** | Post-conversation   | Higher recall, no latency |

### Other Notable Systems

**MemOS** (github.com/MemTensor/MemOS) -- "Memory Operating System" with
standardized MemCube units, async MemScheduler, multi-modal support, graph storage.

**Memori** (github.com/GibsonAI/Memori) -- SQL-native. Pydantic-based extraction
classifies turns into facts, preferences, rules, summaries. Dual ingest: conscious
(startup) + auto (per-query with top-5 retrieval).

**OpenMemory** (github.com/CaviraOSS/OpenMemory) -- Hierarchical Memory
Decomposition across 5 sectors (factual, emotional, temporal, relational,
behavioral). Adaptive decay curves with reinforcement pulses. Native MCP server.

---

## Part 3: Comparative Analysis

### Extraction Approaches

| Platform         | Extraction Model                         | Trigger                  | LLM Calls/Msg        |
| :--------------- | :--------------------------------------- | :----------------------- | :------------------- |
| **Mem0**         | Dedicated 2-phase pipeline               | Every message pair       | 2 (extract + update) |
| **Letta**        | Agent self-editing                       | Agent decides each turn  | 0 extra              |
| **Zep/Graphiti** | Multi-step graph pipeline                | Every episode            | 4-8                  |
| **LangMem**      | Parallel tool calling                    | Configurable             | 1                    |
| **Gobby**        | Disabled batch / unreliable agent-driven | Session end (disabled)   | 1 (when enabled)     |

### Deduplication Strategy

| Platform         | Method                                                                |
| :--------------- | :-------------------------------------------------------------------- |
| **Mem0**         | Vector similarity (top-5) + LLM decision (ADD/UPDATE/DELETE/NONE)     |
| **Letta**        | Agent reads own memory, self-edits                                    |
| **Zep/Graphiti** | Embedding + full-text + LLM; constrained to same entity pairs         |
| **LangMem**      | Existing memories passed to LLM; parallel tool calls                  |
| **Gobby**        | `content_exists()` exact match + Jaccard word overlap (0.8 threshold) |

### Conflict Resolution

| Platform         | Strategy                                                       |
| :--------------- | :------------------------------------------------------------- |
| **Mem0**         | LLM decides UPDATE (overwrite) or DELETE (remove contradicted) |
| **Letta**        | Agent uses `core_memory_replace`                               |
| **Zep/Graphiti** | Bi-temporal: old edge gets `invalid_at`, full history preserved |
| **LangMem**      | `RemoveDoc` + new memory for atomic replacement                |
| **Gobby**        | None. New memories accumulate alongside stale ones.            |

### Key Universal Patterns

1. **LLM-as-Extractor** -- Every system uses an LLM. Core pattern:
   `(conversation + existing memories) -> extraction prompt -> structured JSON`

2. **Context Window Management** -- Systems limit extraction context:
   Mem0 (summary + last 10), Graphiti (current + 4 prev), Letta (full window)

3. **Two Timing Approaches** -- Pipeline (dedicated, can use cheaper models,
   higher quality) vs Agent-driven (zero cost, less reliable)

4. **Deduplication is Universal** -- Embedding similarity as fast first filter,
   LLM comparison as accurate second filter. Scope constraint is critical.

5. **Temporal Tracking is Under-Explored** -- Only Graphiti has serious temporal
   modeling. Most treat memories as timeless, which breaks when facts change.

6. **Extraction Prompt Patterns** -- Role assignment, category enumeration,
   explicit exclusions, JSON format enforcement, few-shot examples

---

## Part 4: Gap Analysis -- Gobby vs Industry

| Gap                            | Gobby Today                                          | Industry Best Practice                                 |
| :----------------------------- | :--------------------------------------------------- | :----------------------------------------------------- |
| **Existing memory awareness**  | Extraction prompt has NO access to existing memories | Mem0/LangMem pass existing memories to LLM             |
| **Update/conflict resolution** | Only `content_exists` exact match                    | LLM-driven ADD/UPDATE/DELETE/NONE decisions            |
| **Extraction timing**          | Disabled batch OR unreliable agent-driven            | Incremental (Mem0) or configurable (LangMem)           |
| **Context for long sessions**  | Last 50 raw turns, no summarization                  | Rolling summary + recent messages (Mem0)               |
| **Memory types**               | Flat facts/patterns only                             | Episodic memories with reasoning chains (LangMem)      |
| **Semantic dedup**             | Jaccard word overlap (crude)                         | Embedding similarity + LLM comparison                  |
| **Memory staleness**           | Time-based importance decay                          | Bi-temporal invalidation (Graphiti), LLM DELETE (Mem0) |

---

## Part 5: Recommended Improvements

### Tier 1: Quick Wins (Low effort, high impact)

#### 1a. Re-enable batch extraction with existing-memory awareness

- Add `memory_extract` back to `session-lifecycle.yaml` `on_session_end`
- Modify `SessionMemoryExtractor` to fetch existing project memories and include them in the prompt
- Add to prompt: "Here are existing memories. Do NOT extract duplicates. If new info contradicts an existing memory, note which to UPDATE."
- Output format: `{"action": "ADD|UPDATE|SKIP", "update_id": "...", "content": "...", ...}`

Files: `src/gobby/memory/extractor.py`, `src/gobby/install/shared/prompts/memory/extract.md`,
`src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml`

#### 1b. Improve the extraction prompt

- Add category-based extraction (adapted for coding: debugging insights, architecture decisions, API behaviors, conventions, gotchas)
- Add few-shot examples of good vs bad extractions (Mem0 best practice)
- Add explicit "DO NOT extract" from system messages / hook injections

Files: `src/gobby/install/shared/prompts/memory/extract.md`

#### 1c. Use session summary instead of raw turns

- `generate_handoff` already produces a session summary at `on_session_end`
- Feed the handoff summary to the extractor instead of raw transcript turns
- Cheaper (fewer tokens) and more focused

Files: `src/gobby/memory/extractor.py`, `src/gobby/workflows/memory_actions.py`

### Tier 2: Medium Effort (Significant quality improvement)

#### 2a. Two-phase extract-then-update pipeline (Mem0 pattern)

- Phase 1: Extract candidate facts from session transcript
- Phase 2: For each candidate, search existing memories by embedding similarity, then LLM decides ADD/UPDATE/DELETE/NONE
- This is the single biggest improvement -- prevents "garbage accumulation" where similar-but-slightly-different memories pile up

Files: `src/gobby/memory/extractor.py` (major refactor)

#### 2b. Embedding-based dedup instead of Jaccard

- Replace `_is_similar()` Jaccard word overlap with embedding cosine similarity
- Gobby currently uses a TF-IDF search backend (a sparse bag-of-words representation), not dense semantic embeddings; adding sentence-transformers or OpenAI embeddings would enable true semantic similarity for dedup
- Even simple sentence-transformers would be far better than word overlap

Files: `src/gobby/memory/extractor.py`

#### 2c. Incremental extraction on significant events

- Extract when significant things happen, not just session end:
  - After a task is closed (extract what was learned)
  - After context compaction (before knowledge is lost)
- Hook into `on_pre_compact` and task close events

Files: `src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml`

### Tier 3: Larger Investments (Advanced capabilities)

#### 3a. Episodic memory type (LangMem pattern)

- Add `Episode` schema: observation -> reasoning -> action -> result
- Capture successful debugging sequences, architectural decisions with rationale
- Higher-value than flat facts for future sessions

#### 3b. Memory update/invalidation

- When extraction identifies a contradiction, UPDATE the existing memory
- Add `updated_at` tracking and `invalidated_by` references
- Simpler than Graphiti's bi-temporal but captures the key benefit

#### 3c. Proactive memory skill enhancement

- Show current relevant memories to the agent (like Letta's in-context core memory)
- If the agent can SEE what it already knows, it makes better decisions about what's new
- Inject top-N memories into tool response when agent calls `create_memory`

---

## Recommended Starting Point

The highest-impact change is **1a + 2a combined**: re-enable batch extraction at
session end with a two-phase pipeline that's aware of existing memories. This is
the Mem0 pattern adapted for Gobby:

1. Session ends -> `generate_handoff` produces summary
2. Summary fed to extraction LLM -> produces candidate facts
3. For each candidate: search existing memories by similarity -> LLM decides ADD/UPDATE/SKIP
4. Execute the decisions (create new, update existing, skip duplicates)

This fixes the core problem: memories accumulate without awareness of what
already exists.

---

## Sources

### Papers & Research

- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/html/2504.19413v1)
- [Graphiti: Temporal Knowledge Graph Architecture](https://arxiv.org/html/2501.13956v1)
- [Memory in the Age of AI Agents Survey](https://arxiv.org/abs/2512.13564)
- [Survey of AI Agent Memory Frameworks (Graphlit)](https://www.graphlit.com/blog/survey-of-ai-agent-memory-frameworks)

### Platform Repositories

- [Mem0](https://github.com/mem0ai/mem0) | [Prompts Source](https://github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py) | [Custom Extraction](https://docs.mem0.ai/open-source/features/custom-fact-extraction-prompt) | [Custom Update](https://docs.mem0.ai/open-source/features/custom-update-memory-prompt)
- [Letta/MemGPT](https://github.com/letta-ai/letta) | [Memory Docs](https://docs.letta.com/guides/agents/memory/) | [MemGPT Concept](https://docs.letta.com/concepts/memgpt/)
- [Graphiti](https://github.com/getzep/graphiti) | [Entity Prompts](https://github.com/getzep/graphiti/blob/5a67e660dce965582ba4b80d3c74f25e7d86f6b3/graphiti_core/prompts/extract_nodes.py) | [Edge Prompts](https://github.com/getzep/graphiti/blob/5a67e660dce965582ba4b80d3c74f25e7d86f6b3/graphiti_core/prompts/extract_edges.py)
- [LangMem](https://github.com/langchain-ai/langmem) | [Conceptual Guide](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) | [Semantic Extraction](https://langchain-ai.github.io/langmem/guides/extract_semantic_memories/) | [Episodic Extraction](https://langchain-ai.github.io/langmem/guides/extract_episodic_memories/) | [API Reference](https://langchain-ai.github.io/langmem/reference/memory/)
- [MemOS](https://github.com/MemTensor/MemOS) | [Memori](https://github.com/GibsonAI/Memori) | [OpenMemory](https://github.com/CaviraOSS/OpenMemory)

### Blog Posts

- [How Three Prompts Created a Viral AI Memory Layer (Mem0)](https://blog.lqhl.me/mem0-how-three-prompts-created-a-viral-ai-memory-layer)

### Key Gobby Files

- `src/gobby/memory/extractor.py` -- SessionMemoryExtractor (batch extraction)
- `src/gobby/install/shared/prompts/memory/extract.md` -- extraction prompt
- `src/gobby/install/shared/workflows/lifecycle/session-lifecycle.yaml` -- lifecycle triggers
- `src/gobby/install/shared/skills/proactive-memory/SKILL.md` -- agent-driven skill
- `src/gobby/workflows/memory_actions.py` -- workflow action handlers
- `src/gobby/sessions/lifecycle.py` -- background transcript processing
- `src/gobby/sync/memories.py` -- JSONL export/import
