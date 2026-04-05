# Plan: Remove LiteLLM Provider and Dependency (#11191)

## Context

LiteLLM is a required dependency (~heavy, pulls in dozens of transitive deps) that Gobby no longer uses for LLM calls. All LLM consumption now routes through CLI/tmux — the CLI handles its own auth (subscription or API key) internally, so Gobby doesn't need to manage auth modes or make direct API calls. LiteLLM as a provider is dead code with zero production call paths. However, it's still load-bearing for three utility functions: model cost population, model discovery for the admin API, and context window resolution for non-Claude models.

This plan removes the provider entirely, replaces those utilities with a maintained static registry, and demotes litellm to an optional dependency — only needed for **remote embeddings** (users on low-end hardware like Raspberry Pi who can't run local nomic embeddings).

## Phase 1: Create `src/gobby/llm/model_registry.py` (new file)

Central replacement for all litellm data lookups. Two data sources:

### Primary: OpenRouter API (dynamic, fetched at startup)
OpenRouter's `GET https://openrouter.ai/api/v1/models` is **public (no auth)** and returns 349+ models with:
- Pricing: `prompt`, `completion`, `input_cache_read`, `input_cache_write` (per-token USD strings)
- Context windows: `context_length`, `max_completion_tokens`
- Architecture: modalities, tokenizer
- Model names with provider prefixes (e.g. `anthropic/claude-opus-4.6`, `openai/gpt-5`)

This replaces both `litellm.model_cost` (pricing) and `_discover_models()` (model lists) in one API call.

### Fallback: DB cache from last successful fetch
The `model_costs` table persists across daemon restarts. If OpenRouter is unreachable on startup, skip the refresh and use cached data from the last successful fetch. Same pattern as the current litellm approach — just a different source. First-ever startup with no cached data gets zero costs (harmless).

### Module contents:
- **`async fetch_models() -> list[ModelInfo]`** — hits OpenRouter, parses response into clean internal format. Filters to providers we care about (anthropic, openai, google). Returns empty list on failure (caller uses cached DB data).
- **Provider prefix mapping** — maps OpenRouter prefixes (`anthropic/`, `openai/`, `google/`) to Gobby provider names (`claude`, `codex`, `gemini`).

No aliases or utility functions needed — `resolve_model_alias` and `get_litellm_model` are only used inside dead code paths being deleted.

## Phase 2: Rewire `model_costs.py`

**File**: `src/gobby/storage/model_costs.py`

- Rename `populate_from_litellm()` → `populate()`
- Replace `import litellm` / iteration over `litellm.model_cost` with iteration over `model_registry.MODEL_COSTS`
- Delete `_apply_anthropic_overrides()` — the hardcoded table IS the source of truth now
- Change `source` column value from `'litellm'` to `'registry'`
- Update docstring/class description

**File**: `src/gobby/runner_init.py` (line 180)
- Change `cost_store.populate_from_litellm()` → `cost_store.populate()`

## Phase 3: Rewire `claude_models.py`

**File**: `src/gobby/llm/claude_models.py` (lines 70-81)

- Replace `import litellm` / `litellm.get_model_info()` fallback with a lookup into the `model_costs` DB table (which now stores `context_length` from OpenRouter alongside pricing)
- Alternatively, add a `model_context_windows` DB table or column populated from OpenRouter's `context_length` field during the same startup fetch
- Keep the `_unused` parameter signature for now (avoids churn at call sites)
- Claude context windows stay hardcoded in `_CLAUDE_CONTEXT_WINDOWS` (already handled, never trusted litellm for Claude)

## Phase 4: Rewire `_config.py`

**File**: `src/gobby/servers/routes/admin/_config.py`

- Replace `_discover_models()` body with `return copy.deepcopy(model_registry.MODELS_BY_PROVIDER)`
- Delete `_PROVIDER_PREFIX_MAP`, `_EXCLUDED_KEYWORDS`, `_MIN_VERSION_FILTERS`, `_model_id_to_label()` — all dead
- Remove `"litellm"` from `_fallback_models_from_config()` provider iteration (line 129)
- Simplify `get_models` endpoint — no try/except needed since discovery can't fail

## Phase 5: Delete dead provider code

**Delete entire files:**
- `src/gobby/llm/litellm.py` (LiteLLMProvider, 302 lines)
- `src/gobby/llm/litellm_utils.py` (124 lines)
- `src/gobby/llm/gemini.py` (GeminiProvider — entirely litellm-routed)

**`src/gobby/llm/claude.py`** — remove all litellm fallback paths:
- Delete `self._litellm` field (line 78)
- Delete `_setup_litellm()` (lines 110-122)
- Delete `elif self._litellm:` branches in `generate_summary`, `generate_text`, `generate_json`, `describe_image`
- Delete `_generate_summary_litellm()`, `_generate_text_litellm()`, `_generate_json_litellm()`, `_describe_image_litellm()`
- Remove `from gobby.llm.litellm_utils import resolve_model_alias` imports
- Remove api_key auth mode litellm setup (lines 92-94) — CLI/tmux handles all auth internally now

**`src/gobby/llm/service.py`:**
- Delete `elif name == "gemini":` block (lines 107-111)
- Delete `elif name == "litellm":` block (lines 113-117)
- Update error message to `"claude, codex"`

**`src/gobby/llm/resolver.py`:**
- Remove `"gemini"` and `"litellm"` from `SUPPORTED_PROVIDERS` (line 26)

**`src/gobby/config/llm_providers.py`:**
- Remove `gemini` field (lines 81-84)
- Remove `litellm` field (lines 85-88)
- Remove corresponding lines from `get_enabled_providers()`
- Update docstring YAML example

**`src/gobby/llm/base.py`:**
- Update docstring references

## Phase 6: Embeddings — demote litellm to optional

**`pyproject.toml`:**
- Move `"litellm>=1.83.0"` from `dependencies` to `[project.optional-dependencies]` under `embeddings = [...]`
- Remove litellm deprecation warning filters (lines 155-156)

**`src/gobby/search/embeddings.py`:**
- Update error message (line 99) to say `"Run: uv sync --extra embeddings"`
- No other changes — the ImportError guard already works correctly

## Phase 7: Schema migration

**`src/gobby/storage/baseline_schema.sql`:**
- Change `source TEXT NOT NULL DEFAULT 'litellm'` → `source TEXT NOT NULL DEFAULT 'registry'` on `model_costs` table

**New migration** (if needed for existing installs):
- `UPDATE model_costs SET source = 'registry' WHERE source = 'litellm'`
- `ALTER TABLE` not needed — just a default value change, handled by repopulation on next startup

## Phase 8: Test cleanup

**Delete:**
- `tests/llm/test_llm_litellm.py`

**Update (remove litellm test methods/fixtures):**
- `tests/llm/test_claude.py` — delete `TestGenerateSummaryLitellm`, `TestGenerateTextLitellm`, litellm paths in `TestGenerateJson`, `TestDescribeImage`, `TestAuthModeSelection.test_setup_litellm_import_error`, `test_api_key_mode_sets_up_litellm`
- `tests/llm/test_claude_provider.py` — delete `MockLiteLLM`, `test_generate_text_api_key_mode`, `test_generate_summary_api_key_mode`, `test_describe_image_api_key_mode`
- `tests/llm/test_generate_json.py` — delete `TestLiteLLMGenerateJson` class and `litellm_config` fixture
- `tests/llm/test_context_window.py` — replace litellm mock tests with `model_registry.CONTEXT_WINDOWS` lookup tests
- `tests/llm/test_cost_table.py` — update to test `populate()` against hardcoded registry
- `tests/config/test_llm_providers.py` — remove gemini/litellm provider config tests
- `tests/servers/routes/test_admin.py` — update model discovery tests
- `tests/llm/test_sdk_utils.py` — update litellm error sanitization test

**Add:**
- `tests/llm/test_model_registry.py` — basic tests for the new static data (costs exist for key models, context windows are sane, model lists have expected structure)

## Phase 9: Documentation

Update litellm references in:
- `docs/guides/configuration.md`
- `docs/architecture/source-tree.md`
- `docs/architecture/technology-stack.md`

## Verification

1. `uv run pytest tests/llm/ -v` — all LLM tests pass
2. `uv run pytest tests/config/ -v` — config tests pass
3. `uv run pytest tests/servers/routes/test_admin.py -v` — admin API tests pass
4. `uv run pytest tests/storage/ -v` — storage/cost tests pass
5. `uv run ruff check src/` — no lint errors
6. `uv run mypy src/gobby/llm/ src/gobby/storage/model_costs.py src/gobby/config/llm_providers.py` — type checks pass
7. Verify `litellm` no longer appears in `uv pip list` after `uv sync` (without `--extra embeddings`)
8. Start daemon, hit `/api/admin/models` — returns static model lists
