---
title: 'gobby-skills: SkillPort-compatible Skill Management'
slug: 'gobby-skills'
created: '2026-01-14'
updated: '2026-01-19'
status: 'draft'
stepsCompleted: []
files_to_modify:
  - src/gobby/storage/skills.py
  - src/gobby/skills/__init__.py
  - src/gobby/skills/parser.py
  - src/gobby/skills/validator.py
  - src/gobby/skills/search.py
  - src/gobby/skills/embeddings.py
  - src/gobby/skills/loader.py
  - src/gobby/skills/updater.py
  - src/gobby/skills/manager.py
  - src/gobby/mcp_proxy/tools/skills.py
  - src/gobby/mcp_proxy/registries.py
  - src/gobby/cli/skills.py
  - src/gobby/cli/__init__.py
  - src/gobby/hooks/skill_injection.py
  - src/gobby/storage/migrations.py
  - CLAUDE.md
code_patterns:
  - InternalToolRegistry pattern from src/gobby/mcp_proxy/tools/internal.py
  - TF-IDF search from src/gobby/memory/search/tfidf.py
  - YAML frontmatter parsing (similar to prompts/loader.py)
  - Storage CRUD from src/gobby/storage/memories.py
  - CLI command group from src/gobby/cli/memory.py
---

## Overview

### Problem Statement

AI agents benefit from structured instructions ("skills") for common tasks like writing commit messages, reviewing PRs, or following coding conventions. Currently, there's no way to store, discover, or inject these skills into Gobby sessions.

SkillPort (github.com/gotalab/skillport) solves this for other AI tools. Gobby should provide **full SkillPort feature parity** plus Gobby-specific advantages, following the Agent Skills specification (agentskills.io).

### Solution

Add a `gobby-skills` internal MCP server with:

1. Full Agent Skills spec compliance (SKILL.md format)
2. All SkillPort CLI commands (list, show, install, remove, update, validate, meta, init, doc, new)
3. All SkillPort MCP tools (list_skills, get_skill, search_skills, install_skill, etc.)
4. TF-IDF search + optional embedding support (like SkillPort)
5. Gobby-specific advantages (project-scoping, hook integration, workflow binding)

### Scope

**In Scope (Full SkillPort Parity):**

- SKILL.md file format with YAML frontmatter (Agent Skills spec)
- SQLite storage for skill metadata
- `gobby-skills` MCP registry with all SkillPort tools
- Import from GitHub repos, local paths, ZIP archives
- TF-IDF search + optional embeddings (multi-provider)
- Category and tag filtering
- Core skills (`alwaysApply` flag)
- Skill update from source
- Full CLI parity: list, show, install, remove, update, validate, meta get/set/unset, init, doc, new
- `--json` output for CI pipelines
- Spec validation

**Gobby Advantages (Beyond SkillPort):**

- Project-scoped skills (vs SkillPort's env var filtering)
- Enable/disable per-skill toggle
- Hook integration (auto-inject core skills at session start)
- Task system integration
- Workflow binding (skills as step requirements)

**Out of Scope (Not in SkillPort either):**

- Skill versioning history/changelog tracking
- Skill marketplace/central registry
- Script execution sandboxing (beyond allowed_commands)
- Skill dependencies (skill A requires skill B)

---

## SkillPort Feature Parity Checklist

| SkillPort Feature | gobby-skills Equivalent | Phase |
|-------------------|------------------------|-------|
| `skillport add <url>` | `gobby skills install <source>` | 5 |
| `skillport update [--all]` | `gobby skills update [name] [--all]` | 5 |
| `skillport list` | `gobby skills list [--category] [--tags] [--json]` | 5 |
| `skillport remove <id>` | `gobby skills remove <name>` | 5 |
| `skillport validate [path]` | `gobby skills validate [path] [--json]` | 5 |
| `skillport meta get/set/unset` | `gobby skills meta get/set/unset` | 5 |
| `skillport init` | `gobby skills init` | 5 |
| `skillport doc` | `gobby skills doc` | 5 |
| `skillport show <id>` | `gobby skills show <name>` | 5 |
| MCP `search_skills(query)` | `search_skills(query, category, tags)` | 4 |
| MCP `load_skill(skill_id)` | `get_skill(name)` | 4 |
| Progressive disclosure | Same (~100 tokens metadata) | 4 |
| GitHub import | GitHub import (all URL formats) | 3 |
| Local directory import | Local directory import | 3 |
| ZIP archive import | ZIP archive import | 3 |
| Category filtering | Category filtering | 2 |
| Tag filtering | Tag filtering (tags_any, tags_all) | 2 |
| `alwaysApply` flag | Core skills + auto-injection | 2, 6 |
| BM25/Tantivy search | TF-IDF search | 2 |
| Optional embeddings (OpenAI) | Optional embeddings (multi-provider) | 2 |
| Validation against spec | Full spec validation | 1 |
| CI-friendly JSON output | `--json` flag | 5 |
| Auto-reindex on changes | Change listeners + reindex | 2 |
| scripts/ directory | scripts/ directory support | 3 |
| references/ directory | references/ directory support | 3 |
| assets/ directory | assets/ directory support | 3 |
| Template scaffolding | `gobby skills new <name>` | 5 |

---

## Architecture

### Component Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Layer (stdio)                        │
│  gobby-skills: list_skills, get_skill, search_skills,           │
│                install_skill, remove_skill, update_skill        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                        SkillManager                              │
│  - load_skill(path) → Skill                                      │
│  - search(query) → list[SkillMetadata]                           │
│  - get_content(skill_id) → str                                   │
│  - update_skill(name) → Skill                                    │
│  - list_core_skills() → list[Skill]                              │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
    ┌───────────────┬─────────────┼─────────────┬──────────────┐
    │               │             │             │              │
┌───▼─────────┐ ┌───▼─────────┐ ┌─▼───────────┐ ┌▼────────────┐ ┌▼──────────┐
│ LocalSkill  │ │ SkillLoader │ │ SkillSearch │ │ SkillUpdate │ │ Validator │
│ Manager     │ │ (parse/load)│ │ (TF-IDF +   │ │ r (refresh) │ │ (spec     │
│ (SQLite)    │ │             │ │ embeddings) │ │             │ │ checks)   │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘
```

### Key Abstractions

**Skill dataclass** (`src/gobby/storage/skills.py`):

```python
@dataclass
class Skill:
    # Identity
    id: str                          # Prefixed ID (skl-...)
    name: str                        # Required, max 64 chars, lowercase+hyphens

    # Agent Skills Spec Fields
    description: str                 # Required, max 1024 chars
    version: str | None              # Optional (from metadata.version)
    license: str | None              # Optional
    compatibility: str | None        # Optional, max 500 chars
    allowed_tools: list[str] | None  # Optional (for tool pre-approval)
    metadata: dict[str, Any] | None  # Free-form extensions
    content: str                     # Full markdown body

    # Source Tracking
    source_path: str                 # File path or URL
    source_type: str                 # 'local', 'github', 'url', 'zip'
    source_ref: str | None           # Git ref (branch/tag/commit) for updates

    # Gobby-specific
    enabled: bool                    # Toggle without removing
    project_id: str | None           # NULL = global, else project-scoped

    # Timestamps
    created_at: str
    updated_at: str
```

**Metadata Structure** (SkillPort-compatible extensions in `metadata.skillport`):

```yaml
---
name: commit-message
description: Generate conventional commit messages following Angular conventions
license: MIT
compatibility: Requires git CLI
metadata:
  author: anthropic
  version: "1.0"
  skillport:                    # SkillPort extensions namespace
    category: git
    tags: [git, commits, workflow]
    alwaysApply: false
  gobby:                        # Gobby extensions namespace
    triggers: ["/commit"]
    workflow_hint: "git-workflow"
allowed-tools: Bash(git:*)
---

# Commit Message Generator

## Instructions
When generating commit messages, follow these conventions...
```

---

## Phase 1: Storage Layer + Parser + Validation

**Goal**: Skill storage with full Agent Skills spec validation.

**Files:**

- `src/gobby/storage/skills.py` - Skill dataclass + LocalSkillManager
- `src/gobby/skills/__init__.py` - Module init
- `src/gobby/skills/parser.py` - YAML frontmatter parser
- `src/gobby/skills/validator.py` - Agent Skills spec validation
- `src/gobby/storage/migrations.py` - Add skills table (v67)

**Tasks:**

- [ ] Create Skill dataclass with all spec fields + Gobby extensions (category: code)
- [ ] Create `validate_skill_name()` per spec: max 64, lowercase+hyphens, no --/leading/trailing - (category: code)
- [ ] Create `validate_skill_description()`: max 1024 chars, non-empty (category: code)
- [ ] Create `validate_skill_compatibility()`: max 500 chars (category: code)
- [ ] Create YAML frontmatter parser for SKILL.md files (category: code)
- [ ] Create `SkillValidator` class with full spec validation (category: code)
- [ ] Create LocalSkillManager with CRUD methods (category: code)
- [ ] Add change listener pattern to LocalSkillManager (category: code)
- [ ] Add skills table migration (v67) (category: config)

**Acceptance Criteria:**

- [ ] Can create, read, update, delete skills in SQLite
- [ ] Name validation rejects: uppercase, leading/trailing hyphens, consecutive hyphens, >64 chars
- [ ] Description validation rejects: empty, >1024 chars
- [ ] Parser extracts all frontmatter fields correctly
- [ ] Change listeners fire on mutations

---

## Phase 2: Search Integration

**Goal**: TF-IDF search with category/tag filtering + optional embeddings.

**Files:**

- `src/gobby/skills/search.py` - SkillSearch class
- `src/gobby/skills/embeddings.py` - Optional embedding provider support
- `src/gobby/skills/manager.py` - SkillManager coordinator

**Tasks:**

- [ ] Create SkillSearch adapting TF-IDF from memory system (category: code)
- [ ] Implement search on name + description + tags + category (category: code)
- [ ] Add category filtering to search (category: code)
- [ ] Add tag filtering (tags_any, tags_all) to search (category: code)
- [ ] Create optional embedding provider abstraction (category: code)
- [ ] Implement OpenAI embedding provider (via existing LLM abstraction) (category: code)
- [ ] Add hybrid search: TF-IDF + optional embedding similarity (category: code)
- [ ] Create SkillManager coordinating storage + search + loader (category: code)
- [ ] Wire change listener to trigger search reindex (category: code)
- [ ] Add `list_core_skills()` for alwaysApply=true skills (category: code)

**Acceptance Criteria:**

- [ ] TF-IDF search returns relevant skills (default, no API needed)
- [ ] Category filtering works: `search_skills(query="...", category="git")`
- [ ] Tag filtering works: `search_skills(query="...", tags_any=["git", "workflow"])`
- [ ] Optional embedding search works when configured
- [ ] Core skills (alwaysApply) can be listed separately
- [ ] Changes trigger search index rebuild

---

## Phase 3: Skill Loader + Updater

**Goal**: Load skills from filesystem, GitHub, and ZIP archives; support updates.

**Files:**

- `src/gobby/skills/loader.py` - SkillLoader class
- `src/gobby/skills/updater.py` - SkillUpdater class

**Tasks:**

- [ ] Create SkillLoader.load_skill(path) method (category: code)
- [ ] Create SkillLoader.load_directory(path) for batch loading (category: code)
- [ ] Add GitHub import support via httpx (category: code)
- [ ] Support GitHub URL formats: `owner/repo`, full URL, branch/path (category: code)
- [ ] Add ZIP archive import support (category: code)
- [ ] Support skill directory structure (scripts/, references/, assets/) (category: code)
- [ ] Store `source_ref` for GitHub imports (branch/commit) (category: code)
- [ ] Create SkillUpdater.update_skill(name) to refresh from source (category: code)
- [ ] Create SkillUpdater.update_all() for bulk refresh (category: code)
- [ ] Validate directory name matches skill name (category: code)

**Acceptance Criteria:**

- [ ] Can load individual SKILL.md files
- [ ] Can load all skills from a directory
- [ ] Can import from `github:owner/repo` and `github:owner/repo/tree/branch/path`
- [ ] Can import from ZIP archives
- [ ] Handles skill directories with scripts/references/assets
- [ ] Can update skills from original source
- [ ] Validates skill directory name matches frontmatter name

---

## Phase 4: MCP Registry

**Goal**: gobby-skills MCP server with all SkillPort-equivalent tools.

**Files:**

- `src/gobby/mcp_proxy/tools/skills.py` - create_skills_registry()
- `src/gobby/mcp_proxy/registries.py` - Register gobby-skills

**Tasks:**

- [ ] Create create_skills_registry() factory function (category: code)
- [ ] Implement `list_skills` tool (metadata only, ~100 tokens each) (category: code)
- [ ] Implement `get_skill` tool (full content + file paths) (category: code)
- [ ] Implement `search_skills` tool with category/tag filtering (category: code)
- [ ] Implement `install_skill` tool (from path/URL/GitHub/ZIP) (category: code)
- [ ] Implement `remove_skill` tool (category: code)
- [ ] Implement `update_skill` tool (refresh from source) (category: code)
- [ ] Implement `list_core_skills` tool (alwaysApply skills) (category: code)
- [ ] Add gobby-skills to setup_internal_registries() (category: config)

**Acceptance Criteria:**

- [ ] gobby-skills appears in list_mcp_servers()
- [ ] list_skills returns lightweight metadata (~100 tokens/skill)
- [ ] get_skill returns full content with references to scripts/assets
- [ ] search_skills supports category and tag filtering
- [ ] install_skill works with all source types

---

## Phase 5: CLI Commands (Full SkillPort Parity)

**Goal**: CLI with all SkillPort commands plus Gobby extras.

**Files:**

- `src/gobby/cli/skills.py` - Click command group
- `src/gobby/cli/__init__.py` - Register skills group

**Tasks:**

- [ ] Create skills command group (category: code)
- [ ] Implement `gobby skills list [--category] [--tags] [--json]` (category: code)
- [ ] Implement `gobby skills show <name> [--json]` (category: code)
- [ ] Implement `gobby skills install <source> [--project]` (category: code)
- [ ] Implement `gobby skills remove <name>` (category: code)
- [ ] Implement `gobby skills update [name] [--all]` (category: code)
- [ ] Implement `gobby skills validate [path] [--json]` (category: code)
- [ ] Implement `gobby skills meta get <skill> <key>` (category: code)
- [ ] Implement `gobby skills meta set <skill> <key> <value>` (category: code)
- [ ] Implement `gobby skills meta unset <skill> <key>` (category: code)
- [ ] Implement `gobby skills init` (create .gobby/skills/ + config) (category: code)
- [ ] Implement `gobby skills new <name>` (scaffold new skill from template) (category: code)
- [ ] Implement `gobby skills doc` (generate AGENTS.md reference table) (category: code)
- [ ] Implement `gobby skills enable/disable <name>` (category: code)
- [ ] Implement `gobby skills sync` (sync filesystem to DB) (category: code)
- [ ] Register skills group in cli/__init__.py (category: config)

**Acceptance Criteria:**

- [ ] All SkillPort CLI commands have equivalents
- [ ] `--json` flag produces CI-friendly JSON output
- [ ] `gobby skills validate` catches all spec violations
- [ ] `gobby skills new` creates a complete skill scaffold
- [ ] `gobby skills doc` generates markdown reference table

---

## Phase 6: Hook Integration (Gobby Advantage)

**Goal**: Integrate skills with Gobby's hook system.

**Files:**

- `src/gobby/hooks/skill_injection.py` - Skill injection logic
- `src/gobby/adapters/claude_code.py` - Update adapter

**Tasks:**

- [ ] Add `inject_core_skills` option to session-start hook (category: code)
- [ ] Implement core skill injection (alwaysApply=true skills) (category: code)
- [ ] Add skill context to session handoff (category: code)
- [ ] Support skill recommendation in suggest_next_task (category: code)

**Acceptance Criteria:**

- [ ] Core skills are automatically injected at session start
- [ ] Skills persist across session handoffs
- [ ] Task suggestions can include relevant skills

---

## Phase 7: Documentation

**Goal**: Comprehensive documentation.

**Files:**

- `CLAUDE.md`
- `docs/guides/skills.md`

**Tasks:**

- [ ] Add gobby-skills to internal MCP servers table in CLAUDE.md (category: docs)
- [ ] Document skill file format (Agent Skills spec) (category: docs)
- [ ] Document all CLI commands (category: docs)
- [ ] Document MCP tools (category: docs)
- [ ] Document Gobby-specific extensions (triggers, project-scoping) (category: docs)
- [ ] Create docs/guides/skills.md user guide (category: docs)

**Acceptance Criteria:**

- [ ] CLAUDE.md documents gobby-skills server and tools
- [ ] Skill file format is documented
- [ ] All CLI commands documented with examples

---

## Dependencies

### External Dependencies

- PyYAML (already in dependencies)
- sklearn (already used by memory system)
- httpx (already in dependencies)

### Blockers

- None

---

## Testing Strategy

### Unit Tests

- Storage CRUD operations
- YAML frontmatter parsing
- Name/description/compatibility validation
- TF-IDF search accuracy
- Embedding search (when configured)
- Tool input validation

### Integration Tests

- Full import flow: GitHub → parse → validate → store → search
- MCP tool round-trip: list → search → get → update
- CLI commands end-to-end
- Hook injection flow

### Manual Verification

1. `gobby skills init` - creates .gobby/skills/
2. `gobby skills new my-skill` - scaffolds template
3. `gobby skills validate ./my-skill` - validates against spec
4. `gobby skills install github:anthropics/skills` - imports from GitHub
5. `gobby skills list --json` - lists with JSON output
6. `gobby skills update --all` - updates from sources
7. Start Claude Code session - verify core skills injected
8. `list_tools(server="gobby-skills")` - verify MCP tools
9. `search_skills(query="commit", category="git")` - verify search

---

## Task Mapping

| Task # | Checkbox | Status |
| :--- | :--- | :--- |

---

## Completion Instructions

When completing a task:

1. Make all code changes
2. Run tests: `uv run pytest tests/skills/ -v`
3. Commit with task reference: `git commit -m "[#N] description"`
4. Close the task: `gobby tasks close #N --commit-sha <sha>`
5. Update the checkbox above to `[x]`

Never close a task without committing first unless it's a non-code task.

---

## Sources

- [SkillPort GitHub](https://github.com/gotalab/skillport)
- [Agent Skills Specification](https://agentskills.io/specification)
- [SkillPort Configuration Guide](https://github.com/gotalab/skillport/blob/main/guide/configuration.md)
- [SkillPort Creating Skills Guide](https://github.com/gotalab/skillport/blob/main/guide/creating-skills.md)
