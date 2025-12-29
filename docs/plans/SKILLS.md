# Plan: Decouple gobby-memory and gobby-skills

## Goal

Full separation of gobby-memory and gobby-skills modules with independent configurations. The gobby-skills module should not import from gobby-memory. Skills content can still reference memory tools.

## Atomic Tasks

### Phase 1: Configuration

- [ ] **SKILL-1**: Add `SkillSyncConfig` class to `src/gobby/config/app.py` (near line 689)
- [ ] **SKILL-2**: Add `skill_sync` field to `DaemonConfig` in `src/gobby/config/app.py`

### Phase 2: Create Skills Module

- [ ] **SKILL-3**: Create `src/gobby/skills/__init__.py` with exports
- [ ] **SKILL-4**: Create `src/gobby/skills/learner.py` (copy from `memory/skills.py`)

### Phase 3: Update Imports

- [ ] **SKILL-5**: Update import in `src/gobby/runner.py:14`
- [ ] **SKILL-6**: Update import in `src/gobby/servers/http.py:30`
- [ ] **SKILL-7**: Update import in `src/gobby/mcp_proxy/registries.py:13`
- [ ] **SKILL-8**: Update import in `src/gobby/mcp_proxy/tools/skills.py:24`
- [ ] **SKILL-9**: Update import in `src/gobby/cli/skills.py:10`
- [ ] **SKILL-10**: Update import in `src/gobby/hooks/hook_manager.py:39`
- [ ] **SKILL-11**: Update import in `tests/mcp_proxy/test_internal_registries.py:8`
- [ ] **SKILL-12**: Update import in `tests/memory/test_skill_learning.py:7`
- [ ] **SKILL-13**: Update import in `tests/workflows/test_memory_actions.py:6`

### Phase 4: Update Runner Config Usage

- [ ] **SKILL-14**: Update `src/gobby/runner.py` to use `skill_sync` config instead of `memory_sync` (lines 121-138)
- [ ] **SKILL-15**: Update runner.py import to get `SkillSyncConfig` from `config.app`

### Phase 5: Clean Up sync/skills.py

- [ ] **SKILL-16**: Remove inline `SkillSyncConfig` class from `src/gobby/sync/skills.py` (lines 23-34)
- [ ] **SKILL-17**: Add import `from gobby.config.app import SkillSyncConfig` to `sync/skills.py`

### Phase 6: Cleanup

- [ ] **SKILL-18**: Delete `src/gobby/memory/skills.py`

### Phase 7: Verification

- [ ] **SKILL-19**: Run `uv run ruff check src/gobby/` and fix any issues
- [ ] **SKILL-20**: Run `uv run mypy src/gobby/` and fix any type errors
- [ ] **SKILL-21**: Run `uv run pytest tests/ -v` and ensure all tests pass

## Files Summary

**New:**
- `src/gobby/skills/__init__.py`
- `src/gobby/skills/learner.py`

**Modified:**
- `src/gobby/config/app.py`
- `src/gobby/runner.py`
- `src/gobby/sync/skills.py`
- `src/gobby/servers/http.py`
- `src/gobby/mcp_proxy/registries.py`
- `src/gobby/mcp_proxy/tools/skills.py`
- `src/gobby/cli/skills.py`
- `src/gobby/hooks/hook_manager.py`
- `tests/mcp_proxy/test_internal_registries.py`
- `tests/memory/test_skill_learning.py`
- `tests/workflows/test_memory_actions.py`

**Deleted:**
- `src/gobby/memory/skills.py`
