# LLMLingua-2 Compression + Enhanced Capture Integration

## Overview

Integrate LLMLingua-2 prompt compression at retrieval/injection time across session handoffs, memories, and context resolution. Store verbose content, compress when injecting into LLM context. Complements existing `to_brief()` pattern (schema field selection) with semantic text compression.

## Module Structure

```
src/gobby/compression/
    __init__.py           # Public API: TextCompressor, CompressionConfig
    compressor.py         # LLMLingua-2 wrapper with caching + fallback
    config.py             # Pydantic config model
```

## Key Design Decisions

1. **Compression at retrieval time** - Store uncompressed, compress when needed
2. **Lazy model loading** - Only load 400MB model when first compression requested
3. **Graceful degradation** - Falls back to smart truncation if LLMLingua unavailable
4. **Per-use-case ratios** - Different compression for handoffs (0.5) vs memories (0.6) vs context (0.4)
5. **Optional dependency** - System works without llmlingua installed

## Enhanced Capture Limits (with compression enabled)

| System | Current | Enhanced |
|--------|---------|----------|
| Handoff turns | 50 | 100 |
| Handoff analyzer turns | 100 | 200 |
| Recent tools captured | 5 | 10 |
| Context resolver max | 50KB | 100KB (->30KB after compression) |
| Transcript messages | 100 | 200 |

## Implementation Tasks

### Phase 1: Compression Module

1. **Create `src/gobby/compression/config.py`**
   - `CompressionConfig` Pydantic model
   - Fields: enabled, model, device, cache settings, per-use-case ratios, thresholds

2. **Create `src/gobby/compression/compressor.py`**
   - `TextCompressor` class with lazy LLMLingua initialization
   - `compress(content, ratio, context_type)` method
   - Hash-based caching with TTL
   - `_fallback_truncate()` for graceful degradation
   - Auto device detection (cuda/mps/cpu)

3. **Create `src/gobby/compression/__init__.py`**
   - Export `TextCompressor`, `CompressionConfig`

4. **Update `pyproject.toml`**
   - Add optional `[compression]` extras: llmlingua, transformers, torch

### Phase 2: Config Integration

5. **Update `src/gobby/config/app.py`**
   - Add `compression: CompressionConfig` field to `DaemonConfig`
   - Add `get_compression_config()` method

### Phase 3: Session Handoff Integration

6. **Update `src/gobby/workflows/summary_actions.py`**
   - `generate_summary()`: Accept `compressor` param, increase `max_turns` when enabled
   - Compress `transcript_summary` before LLM call

7. **Update `src/gobby/workflows/context_actions.py`**
   - `extract_handoff_context()`: Accept `compressor` param, increase limits
   - Compress markdown before `update_compact_markdown()`

8. **Update `src/gobby/sessions/analyzer.py`**
   - `extract_handoff_context()`: Increase `max_turns` default, capture more tools

### Phase 4: Memory Integration

9. **Update `src/gobby/memory/context.py`**
   - `build_memory_context()`: Accept `compressor` param
   - Compress inner content when over threshold

10. **Update `src/gobby/memory/manager.py`**
    - `MemoryManager.__init__()`: Accept `compressor` param
    - Add `recall_as_context()` convenience method with compression

### Phase 5: Context Resolver Integration

11. **Update `src/gobby/agents/context.py`**
    - `ContextResolver.__init__()`: Accept `compressor`, increase limits when enabled
    - `resolve()`: Compress before returning
    - Add `_resolve_raw()` for uncompressed resolution

### Phase 6: ActionExecutor Wiring

12. **Update `src/gobby/workflows/actions.py`**
    - `ActionExecutor.__init__()`: Create `TextCompressor` from config
    - Pass compressor to `generate_summary`, `extract_handoff_context`

### Phase 7: MCP Tools Integration

13. **Update `src/gobby/mcp_proxy/tools/memory.py`**
    - Pass compressor to memory manager for `recall` tool

14. **Update `src/gobby/mcp_proxy/tools/agents.py`**
    - Pass compressor to `ContextResolver` for subagent context injection

### Phase 8: Tests

15. **Create `tests/compression/test_compressor.py`**
    - Skip short content test
    - Disabled fallback test
    - Truncation fallback test
    - Cache hit test
    - `@pytest.mark.slow` actual compression test

16. **Create `tests/compression/test_config.py`**
    - Config validation tests
    - Default values tests

17. **Update integration tests**
    - Handoff with compression
    - Memory injection with compression
    - Context resolver with compression

## Critical Files

| File | Change |
|------|--------|
| `src/gobby/compression/compressor.py` | NEW - Core compressor |
| `src/gobby/compression/config.py` | NEW - Config model |
| `src/gobby/config/app.py` | Add compression field |
| `src/gobby/workflows/summary_actions.py` | Compressor integration |
| `src/gobby/workflows/context_actions.py` | Compressor integration |
| `src/gobby/memory/context.py` | Compressor integration |
| `src/gobby/agents/context.py` | Compressor integration |
| `src/gobby/workflows/actions.py` | Create/pass compressor |
| `pyproject.toml` | Optional dependency |

## Configuration Example

```yaml
# ~/.gobby/config.yaml
compression:
  enabled: true
  model: "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
  device: "auto"
  cache_enabled: true
  cache_ttl_seconds: 3600
  handoff_compression_ratio: 0.5
  memory_compression_ratio: 0.6
  context_compression_ratio: 0.4
  min_content_length: 500
  fallback_on_error: true
```

## Installation

```bash
# Basic (CPU)
uv pip install gobby[compression]

# With GPU
uv pip install gobby[compression] torch --index-url https://download.pytorch.org/whl/cu118
```

## Verification

1. Enable compression in config
2. Create a session with substantial transcript (50+ turns)
3. Trigger handoff via `/compact` or session end
4. Verify `compact_markdown` is shorter than uncompressed would be
5. Spawn subagent, verify context injection is compressed
6. Create memories, verify `recall` returns compressed context
7. Run `uv run pytest tests/compression/` - all pass
8. Run `uv run pytest -m integration` - compression integration tests pass
