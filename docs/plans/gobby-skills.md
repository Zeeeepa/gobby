---
title: 'gobby-skills: SkillPort-compatible Skill Management'
slug: 'gobby-skills'
created: '2026-01-14'
status: 'draft'
stepsCompleted: []
files_to_modify:
  - src/gobby/mcp_proxy/registries.py
  - src/gobby/storage/migrations.py
code_patterns:
  - InternalToolRegistry pattern from src/gobby/mcp_proxy/tools/internal.py
  - TF-IDF search from src/gobby/memory/search/tfidf.py
  - YAML frontmatter parsing (similar to spec_parser.py)
---

## Overview

### Problem Statement

AI agents benefit from structured instructions ("skills") for common tasks like writing commit messages, reviewing PRs, or following coding conventions. Currently, there's no way to store, discover, or inject these skills into Gobby sessions.

SkillPort (github.com/gotalab/skillport) solves this for other AI tools. Gobby should provide compatible skill management that integrates with its existing MCP proxy architecture.

### Solution

Add a `gobby-skills` internal MCP server that:

1. Stores skills as markdown files with YAML frontmatter (SkillPort format)
2. Uses progressive disclosure (lightweight metadata until full content needed)
3. Integrates with existing hook system for context injection
4. Provides CLI commands for skill management

### Scope

**In Scope:**

- SKILL.md file format with YAML frontmatter
- SQLite storage for skill metadata
- `gobby-skills` MCP registry with CRUD + search tools
- Import from GitHub repos (SkillPort-compatible)
- TF-IDF search for skill discovery
- CLI commands (`gobby skills list|show|install|remove`)

**Out of Scope:**

- Skill versioning/updates (future)
- Skill marketplace/registry (future)
- Auto-injection based on context detection (future - agent-driven for now)

## Architecture

### Component Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Layer (stdio)                        │
│  gobby-skills: list_skills, get_skill, search_skills, etc.      │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                        SkillManager                              │
│  - load_skill(path) → Skill                                      │
│  - search(query) → list[SkillMetadata]                           │
│  - get_content(skill_id) → str                                   │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
    ┌─────────────────────────────┼─────────────────────────────┐
    │                             │                             │
┌───▼───────────────┐    ┌───────▼───────────┐    ┌────────────▼────┐
│   SkillStorage    │    │    SkillLoader    │    │   SkillSearch   │
│   (SQLite CRUD)   │    │  (SKILL.md parse) │    │   (TF-IDF)      │
└───────────────────┘    └───────────────────┘    └─────────────────┘
```

### Data Flow

**Skill Discovery (MCP proxy pattern):**

```text
1. list_skills()        → Lightweight metadata (~100 tokens/skill)
2. search_skills(query) → TF-IDF search on descriptions/tags
3. get_skill(name)      → Full skill content (on demand)
```

**Skill Import:**

```text
1. User: gobby skills install github:anthropics/skills
2. SkillLoader fetches SKILL.md files from repo
3. Parser extracts frontmatter + content
4. SkillStorage inserts into SQLite
5. SkillSearch reindexes for TF-IDF
```

### Key Abstractions

**Skill dataclass** (`src/gobby/storage/skills.py`):

```python
@dataclass
class Skill:
    id: str              # Prefixed ID (skl-...)
    name: str            # Unique name (e.g., "commit-message")
    description: str     # Short description for search
    version: str | None
    category: str | None
    tags: list[str]
    triggers: list[str]  # Slash commands (e.g., ["/commit"])
    content: str         # Full markdown content
    source_path: str     # File path or URL
    source_type: str     # 'local', 'github', 'url'
    enabled: bool
    project_id: str | None  # NULL = global
    created_at: datetime
    updated_at: datetime
```

**Skill File Format** (SkillPort-compatible):

```markdown
---
name: commit-message
description: Generate conventional commit messages
version: 1.0.0
metadata:
  category: git
  tags: [git, commits, workflow]
  triggers: ["/commit"]
---

# Commit Message Generator

## Instructions
When generating commit messages, follow these conventions...
```

## Codebase Patterns

### Existing Patterns to Follow

1. **InternalToolRegistry**: Use decorator-based tool registration (see memory, workflows)
2. **Progressive disclosure**: `list_*` returns metadata, `get_*` returns full content
3. **TF-IDF search**: Reuse sklearn pattern from memory system
4. **YAML frontmatter**: Parse like spec documents (similar to spec_parser.py)
5. **Registry setup**: Add to `setup_internal_registries()` in registries.py

### Files to Reference

| File | Purpose |
| :--- | :--- |
| `src/gobby/mcp_proxy/tools/memory.py` | Registry pattern, TF-IDF integration |
| `src/gobby/mcp_proxy/tools/internal.py` | InternalToolRegistry, @registry.tool decorator |
| `src/gobby/mcp_proxy/registries.py` | Where to register gobby-skills |
| `src/gobby/memory/search/tfidf.py` | TF-IDF search implementation to adapt |
| `src/gobby/storage/memories.py` | Storage CRUD pattern |
| `src/gobby/tasks/spec_parser.py` | Markdown parsing patterns |

## Design Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| Storage backend | SQLite | Already in use, no new dependencies |
| File format | SKILL.md + YAML frontmatter | SkillPort compatibility |
| Search | TF-IDF (reuse from memory) | No external dependencies, proven pattern |
| Discovery | MCP proxy pattern | Consistent with existing tools |
| Trigger handling | Agent-driven | Agent decides when to load skills |

## Phase 1: Storage Layer

**Goal**: Skill storage and CRUD operations.

**Files:**

- `src/gobby/storage/skills.py` - Skill dataclass + LocalSkillManager
- `src/gobby/storage/migrations.py` - Add skills table migration

**Tasks:**

- [ ] Create Skill dataclass with all fields (id, name, description, version, category, tags, triggers, content, source_path, source_type, enabled, project_id, timestamps)
- [ ] Create LocalSkillManager with CRUD methods (create, get, list, update, delete)
- [ ] Add skills table migration to migrations.py
- [ ] Add tag filtering support (tags_any, tags_all patterns from memories)
- [ ] Add unit tests for storage layer

**Acceptance Criteria:**

- [ ] Can create, read, update, delete skills in SQLite
- [ ] Tag filtering works correctly
- [ ] Tests pass with 80%+ coverage

## Phase 2: Skill Loader

**Goal**: Parse SKILL.md files and import from sources.

**Files:**

- `src/gobby/skills/__init__.py` - Module init
- `src/gobby/skills/loader.py` - SkillLoader class
- `src/gobby/skills/parser.py` - YAML frontmatter parser

**Tasks:**

- [ ] Create YAML frontmatter parser for SKILL.md files (depends: Phase 1)
- [ ] Create SkillLoader.load_skill(path) method
- [ ] Create SkillLoader.load_directory(path) for batch loading
- [ ] Add GitHub repo import support (fetch raw SKILL.md files)
- [ ] Add validation for required fields (name, description)
- [ ] Add unit tests for loader

**Acceptance Criteria:**

- [ ] Can parse SKILL.md files with YAML frontmatter
- [ ] Can load all skills from a directory
- [ ] Can import from GitHub repos

## Phase 3: Search Integration

**Goal**: TF-IDF search for skill discovery.

**Files:**

- `src/gobby/skills/search.py` - SkillSearch class
- `src/gobby/skills/manager.py` - SkillManager (coordinator)

**Tasks:**

- [ ] Create SkillSearch class adapting TF-IDF from memory/search/ (depends: Phase 2)
- [ ] Implement search on name + description + tags
- [ ] Add category filtering to search
- [ ] Create SkillManager that coordinates storage + loader + search
- [ ] Add lazy initialization for search backend
- [ ] Add unit tests for search

**Acceptance Criteria:**

- [ ] TF-IDF search finds relevant skills by query
- [ ] Category filtering works
- [ ] Search is lazy-initialized (no sklearn import until needed)

## Phase 4: MCP Registry

**Goal**: gobby-skills MCP server with tools.

**Files:**

- `src/gobby/mcp_proxy/tools/skills.py` - create_skills_registry()
- `src/gobby/mcp_proxy/registries.py` - Register gobby-skills

**Tasks:**

- [ ] Create create_skills_registry() factory function (depends: Phase 3)
- [ ] Implement list_skills tool (metadata only, ~100 tokens each)
- [ ] Implement get_skill tool (full content)
- [ ] Implement search_skills tool (TF-IDF search)
- [ ] Implement install_skill tool (from path/URL/GitHub)
- [ ] Implement remove_skill tool
- [ ] Add gobby-skills to setup_internal_registries()
- [ ] Add integration tests for MCP tools

**Acceptance Criteria:**

- [ ] gobby-skills appears in list_mcp_servers()
- [ ] list_skills returns lightweight metadata
- [ ] get_skill returns full skill content
- [ ] search_skills finds relevant skills
- [ ] install_skill imports from GitHub repos

## Phase 5: CLI Commands

**Goal**: CLI for skill management.

**Files:**

- `src/gobby/cli/skills.py` - Click command group
- `src/gobby/cli/__init__.py` - Register skills group

**Tasks:**

- [ ] Create skills command group in cli/skills.py (depends: Phase 4)
- [ ] Implement `gobby skills list` command
- [ ] Implement `gobby skills show <name>` command
- [ ] Implement `gobby skills install <source>` command
- [ ] Implement `gobby skills remove <name>` command
- [ ] Implement `gobby skills sync` command (sync file system to DB)
- [ ] Register skills group in `cli/__init__.py`
- [ ] Add CLI integration tests

**Acceptance Criteria:**

- [ ] `gobby skills list` shows installed skills
- [ ] `gobby skills install github:anthropics/skills` imports skills
- [ ] `gobby skills show commit-message` displays full content

## Phase 6: Documentation

**Goal**: Update docs and CLAUDE.md.

**Files:**

- `CLAUDE.md` - Add skills section
- `docs/guides/skills.md` - User guide (if requested)

**Tasks:**

- [ ] Add gobby-skills to internal MCP servers table in CLAUDE.md (parallel)
- [ ] Document skill file format in CLAUDE.md
- [ ] Add skills CLI commands to CLAUDE.md

**Acceptance Criteria:**

- [ ] CLAUDE.md documents gobby-skills server and tools
- [ ] Skill file format is documented

## Dependencies

### External Dependencies

- PyYAML (already in dependencies)
- sklearn (already used by memory system)

### Blockers

- None

## Testing Strategy

### Unit Tests

- Storage CRUD operations
- YAML frontmatter parsing
- TF-IDF search accuracy
- Tool input validation

### Integration Tests

- Full import flow: GitHub → parse → store → search
- MCP tool round-trip: list → search → get
- CLI commands

### Manual Verification

1. `gobby skills install github:anthropics/skills`
2. `gobby skills list` - verify skills imported
3. Start Claude Code session
4. `list_tools(server="gobby-skills")` - verify tools appear
5. `search_skills(query="commit")` - verify search works
6. `get_skill(name="commit-message")` - verify full content returned

## Task Mapping

<!-- Populated by parse_spec, maintained by agents -->

| Task # | Checkbox | Status |
| :--- | :--- | :--- |

## Completion Instructions

When completing a task:

1. Make all code changes
2. Run tests: `uv run pytest tests/skills/ -v`
3. Commit with task reference: `git commit -m "[#N] description"`
4. Close the task: `gobby tasks close #N --commit-sha <sha>`
5. Update the checkbox above to `[x]`

Never close a task without committing first unless it's a non-code task.
