# Plan: Unified /gobby Skill & MCP Router (Revised)

**Epic:** #6086
**Session:** 39053109-12aa-41c0-8293-dded645dbe27

## Goal

Create a single `/gobby` slash command that routes to both Gobby skills AND MCP servers, eliminating duplicate skill installations and providing a consistent UX.

## Key Discovery (Context7 Research)

Both **Claude Code** and **Gemini CLI** support the same **SKILL.md format** (Markdown + YAML frontmatter). This simplifies the plan significantly:

| CLI | Format | Location |
|-----|--------|----------|
| Claude Code | SKILL.md | `.claude/commands/` |
| Gemini CLI | SKILL.md | `.gemini/skills/*/SKILL.md` |
| Codex CLI | N/A | No slash commands (uses AGENTS.md for instructions only) |

## Problem Analysis

Current state is inconsistent:
- Quick-create skills (bug, nit, feat) duplicated: slash commands in `.claude/commands/gobby/` AND in gobby-skills database
- Full skills (gobby-plan, gobby-tasks) are MCP-only - `/gobby-plan` doesn't work as a slash command
- Skill names have redundant `gobby-` prefix (e.g., `/gobby gobby-plan` instead of `/gobby plan`)
- `alwaysApply` only supports nested format (`metadata.skillport.alwaysApply`)
- No category field for filtering core vs user skills

## Files to Modify

### Phase 1: Router Skill (Shared Format)

| File | Change |
|------|--------|
| `src/gobby/install/shared/skills/gobby-router/SKILL.md` | **NEW** - Unified router skill |
| `src/gobby/install/shared/skills/g/SKILL.md` | **NEW** - Alias skill (includes gobby-router) |
| `src/gobby/adapters/claude_code.py` | Update install to copy router to `.claude/commands/gobby.md` |
| `src/gobby/adapters/gemini.py` | Update install to copy router to `.gemini/skills/gobby-router/` |

### Phase 2: Delete Duplicates

| File | Change |
|------|--------|
| `src/gobby/install/claude/commands/gobby/` | **DELETE** - Remove duplicate slash commands (7 files) |

### Phase 3: Parser/Storage Updates

| File | Change |
|------|--------|
| `src/gobby/skills/parser.py` | Support top-level `alwaysApply` and `category` |
| `src/gobby/storage/skills.py` | Support top-level `alwaysApply` and `category` |

### Phase 4: Skill Renames

| File | Change |
|------|--------|
| `src/gobby/install/shared/skills/gobby-*/` | **RENAME** - Remove gobby- prefix (13 directories) |
| `src/gobby/install/shared/skills/*/SKILL.md` | Add `category: core` and update names (24 files) |

## Expansion Spec

```json
{
  "subtasks": [
    {
      "title": "Create /gobby router skill (SKILL.md)",
      "category": "code",
      "depends_on": [],
      "priority": 1,
      "validation": "File exists at src/gobby/install/shared/skills/gobby-router/SKILL.md with routing logic",
      "description": "Create src/gobby/install/shared/skills/gobby-router/SKILL.md that routes /gobby <skill> to gobby-skills MCP and /gobby mcp <server> to MCP servers. Include help display when no args or 'help' arg. Use standard SKILL.md format (YAML frontmatter + Markdown body)."
    },
    {
      "title": "Create /g alias skill",
      "category": "code",
      "depends_on": [0],
      "priority": 2,
      "validation": "File exists at src/gobby/install/shared/skills/g/SKILL.md that references gobby-router",
      "description": "Create src/gobby/install/shared/skills/g/SKILL.md as shorthand alias for /gobby. Can simply include/reference the gobby-router skill."
    },
    {
      "title": "Update Claude Code adapter to install router",
      "category": "code",
      "depends_on": [0],
      "priority": 1,
      "validation": "gobby install copies gobby-router skill to .claude/commands/gobby.md",
      "description": "Update src/gobby/adapters/claude_code.py install logic to copy the gobby-router SKILL.md to .claude/commands/gobby.md (flattened, not in skills subdirectory since Claude uses commands/ directly)."
    },
    {
      "title": "Update Gemini adapter to install router",
      "category": "code",
      "depends_on": [0],
      "priority": 1,
      "validation": "gobby install copies gobby-router skill to .gemini/skills/gobby-router/SKILL.md",
      "description": "Update src/gobby/adapters/gemini.py install logic to copy the gobby-router skill directory to .gemini/skills/gobby-router/."
    },
    {
      "title": "Delete duplicate slash commands in gobby/ directory",
      "category": "code",
      "depends_on": [2],
      "priority": 1,
      "validation": "Directory src/gobby/install/claude/commands/gobby/ no longer exists",
      "description": "Delete src/gobby/install/claude/commands/gobby/ directory containing bug.md, chore.md, epic.md, eval.md, feat.md, nit.md, ref.md. These are already in gobby-skills and accessible via /gobby bug, etc."
    },
    {
      "title": "Support top-level alwaysApply in parser.py",
      "category": "code",
      "depends_on": [],
      "priority": 1,
      "validation": "Tests pass. ParsedSkill.is_always_apply() returns True for both top-level and nested formats.",
      "description": "TDD: 1) Write tests in tests/skills/test_parser.py for is_always_apply() with both formats: top-level `alwaysApply: true` and nested `metadata.skillport.alwaysApply: true`. 2) Run tests (expect fail). 3) Update is_always_apply() in src/gobby/skills/parser.py to check self.metadata.get('alwaysApply') first, then fall back to nested. 4) Run tests (expect pass)."
    },
    {
      "title": "Support top-level alwaysApply in storage/skills.py",
      "category": "code",
      "depends_on": [5],
      "priority": 1,
      "validation": "Tests pass. Skill.is_always_apply() returns True for both formats.",
      "description": "TDD: 1) Write tests in tests/storage/test_skills.py for Skill.is_always_apply() with both formats. 2) Run tests (expect fail). 3) Update is_always_apply() in src/gobby/storage/skills.py to check self.metadata.get('alwaysApply') first. 4) Run tests (expect pass)."
    },
    {
      "title": "Support top-level category in parser.py and storage",
      "category": "code",
      "depends_on": [5],
      "priority": 2,
      "validation": "Tests pass. get_category() returns value from top-level category or nested metadata.skillport.category.",
      "description": "TDD: 1) Write tests for get_category() in both parser.py and storage/skills.py checking top-level `category: core` and nested format. 2) Run tests (expect fail). 3) Update get_category() to check top-level first. 4) Run tests (expect pass)."
    },
    {
      "title": "Rename gobby-agents skill to agents",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to agents/, SKILL.md has name: agents and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-agents/ to agents/. Update SKILL.md: change name field to 'agents', add 'category: core', update description to remove /gobby-agents references."
    },
    {
      "title": "Rename gobby-clones skill to clones",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to clones/, SKILL.md has name: clones and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-clones/ to clones/. Update SKILL.md: change name field to 'clones', add 'category: core'."
    },
    {
      "title": "Rename gobby-diagnostic skill to diagnostic",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to diagnostic/, SKILL.md has name: diagnostic and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-diagnostic/ to diagnostic/. Update SKILL.md: change name field to 'diagnostic', add 'category: core'."
    },
    {
      "title": "Rename gobby-expand skill to expand",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to expand/, SKILL.md has name: expand and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-expand/ to expand/. Update SKILL.md: change name field to 'expand', add 'category: core'."
    },
    {
      "title": "Rename gobby-mcp skill to mcp-guide",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to mcp-guide/, SKILL.md has name: mcp-guide and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-mcp/ to mcp-guide/ (not 'mcp' to avoid conflict with /gobby mcp route). Update SKILL.md."
    },
    {
      "title": "Rename gobby-memory skill to memory",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to memory/, SKILL.md has name: memory and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-memory/ to memory/. Update SKILL.md."
    },
    {
      "title": "Rename gobby-merge skill to merge",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to merge/, SKILL.md has name: merge and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-merge/ to merge/. Update SKILL.md."
    },
    {
      "title": "Rename gobby-metrics skill to metrics",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to metrics/, SKILL.md has name: metrics and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-metrics/ to metrics/. Update SKILL.md."
    },
    {
      "title": "Rename gobby-plan skill to plan",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to plan/, SKILL.md has name: plan and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-plan/ to plan/. Update SKILL.md."
    },
    {
      "title": "Rename gobby-sessions skill to sessions",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to sessions/, SKILL.md has name: sessions and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-sessions/ to sessions/. Update SKILL.md."
    },
    {
      "title": "Rename gobby-tasks skill to tasks",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to tasks/, SKILL.md has name: tasks and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-tasks/ to tasks/. Update SKILL.md."
    },
    {
      "title": "Rename gobby-workflows skill to workflows",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to workflows/, SKILL.md has name: workflows and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-workflows/ to workflows/. Update SKILL.md."
    },
    {
      "title": "Rename gobby-worktrees skill to worktrees",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 2,
      "validation": "Directory renamed to worktrees/, SKILL.md has name: worktrees and category: core",
      "description": "Rename src/gobby/install/shared/skills/gobby-worktrees/ to worktrees/. Update SKILL.md."
    },
    {
      "title": "Add category: core to quick-create skills",
      "category": "config",
      "depends_on": [7],
      "priority": 2,
      "validation": "All 7 quick-create skills have category: core in SKILL.md",
      "description": "Add 'category: core' to SKILL.md frontmatter for: bug, chore, epic, eval, feat, nit, ref."
    },
    {
      "title": "Add category: core and alwaysApply to foundational skills",
      "category": "config",
      "depends_on": [6, 7],
      "priority": 1,
      "validation": "starting-sessions, claiming-tasks, discovering-tools have both category: core and alwaysApply: true",
      "description": "Update SKILL.md for starting-sessions, claiming-tasks, discovering-tools, committing-changes to add 'category: core' and 'alwaysApply: true' (except committing-changes which shouldn't be alwaysApply)."
    },
    {
      "title": "Restart daemon and verify skill sync",
      "category": "manual",
      "depends_on": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22],
      "priority": 3,
      "validation": "list_skills() shows skills with updated names. No gobby- prefix. Category filtering works.",
      "description": "Run 'uv run gobby restart'. Verify: 1) list_skills() shows skills without gobby- prefix. 2) list_skills(category='core') returns only core skills."
    },
    {
      "title": "Run test suite",
      "category": "manual",
      "depends_on": [5, 6, 7],
      "priority": 3,
      "validation": "All tests pass",
      "description": "Run: uv run pytest tests/skills/ tests/storage/test_skills.py -v"
    }
  ]
}
```

## Verification Checklist

After implementation, verify:

1. **Router works (Claude Code):**
   - `/gobby` or `/gobby help` shows help display
   - `/gobby plan` loads plan skill
   - `/gobby tasks` loads tasks skill
   - `/gobby bug fix login` creates bug task
   - `/g plan` works as alias

2. **Router works (Gemini CLI):**
   - Same commands work in Gemini CLI
   - Skill format is identical

3. **MCP routing works:**
   - `/gobby mcp context7 react docs` routes to context7

4. **No duplicates:**
   - `src/gobby/install/claude/commands/gobby/` directory removed
   - Skills accessible only via /gobby <name>

5. **alwaysApply works:**
   - Both formats supported: `alwaysApply: true` and `metadata.skillport.alwaysApply: true`

6. **Category filtering works:**
   - `list_skills(category="core")` returns only Gobby skills
   - All Gobby skills have `category: "core"`

7. **Skill names updated:**
   - No more `gobby-` prefix in skill names
   - `/gobby plan` not `/gobby gobby-plan`

8. **Tests pass:**
   - `uv run pytest tests/skills/ -v`
   - `uv run pytest tests/storage/test_skills.py -v`

## Sources

- [Context7: Gemini CLI Skills](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md) - SKILL.md format
- [Context7: Claude Code Commands](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/command-development/README.md) - Same format
- [Context7: Codex CLI](https://github.com/openai/codex/blob/main/codex-cli/README.md) - AGENTS.md only, no slash commands
