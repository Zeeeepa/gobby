# Gobby Skills Reference

This directory contains human-readable copies of the skills bundled with Gobby.

**Note**: These are mirrors of the skills in `src/gobby/install/shared/skills/`. For pip/uvx users, the canonical skills are synced to the Gobby database on daemon start and accessed via MCP tools:

```python
# List available skills
list_skills()

# Get a specific skill
get_skill(name="gobby-tasks")

# Search for skills
search_skills(query="task management")
```

## Available Skills

### Macro Skills (Server-Mapped)

These skills provide comprehensive guidance for Gobby's internal MCP servers:

| Skill | Description |
|-------|-------------|
| [gobby-tasks](./gobby-tasks/SKILL.md) | Task management - create, expand, close, and validate tasks |
| [gobby-sessions](./gobby-sessions/SKILL.md) | Session handoff and context preservation |
| [gobby-memory](./gobby-memory/SKILL.md) | Persistent memory across sessions |
| [gobby-workflows](./gobby-workflows/SKILL.md) | Workflow activation and state management |
| [gobby-agents](./gobby-agents/SKILL.md) | Agent spawning and orchestration |
| [gobby-worktrees](./gobby-worktrees/SKILL.md) | Git worktree management for parallel work |
| [gobby-clones](./gobby-clones/SKILL.md) | Git clone management for isolated development |
| [gobby-merge](./gobby-merge/SKILL.md) | AI-powered merge conflict resolution |
| [gobby-metrics](./gobby-metrics/SKILL.md) | Tool usage and performance metrics |
| [gobby-mcp](./gobby-mcp/SKILL.md) | MCP server discovery and tool proxying |
| [gobby-expand](./gobby-expand/SKILL.md) | LLM-powered task expansion |
| [gobby-plan](./gobby-plan/SKILL.md) | Structured specification planning |

### Micro Skills (Guardrails)

These smaller skills provide remediation guidance when agents get stuck:

| Skill | Description |
|-------|-------------|
| [starting-sessions](./starting-sessions/SKILL.md) | Session startup checklist (first 5 things to do) |
| [claiming-tasks](./claiming-tasks/SKILL.md) | Quick fix for "no active task" blocks |
| [discovering-tools](./discovering-tools/SKILL.md) | Progressive disclosure pattern for tools and skills |
| [committing-changes](./committing-changes/SKILL.md) | Commit message format and task close workflow |

## Skill Format

Each skill follows the [Agent Skills specification](https://agentskills.io):

```markdown
---
name: skill-name
description: One-line description (used for discovery)
---

# Skill Title

Detailed content...
```

## Updating Skills

If you modify skills in `src/gobby/install/shared/skills/`, run:

```bash
# Re-sync to docs/skills/
for skill in src/gobby/install/shared/skills/*/; do
  skill_name=$(basename "$skill")
  cp -r "$skill" "docs/skills/"
done
```

Or manually copy the updated SKILL.md files.
