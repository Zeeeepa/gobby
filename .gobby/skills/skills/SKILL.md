---
name: skills
description: This skill should be used when the user asks to "/skills", "list skills", "create skill", "learn skill". Manage reusable instruction templates - list, create, learn from sessions, and export.
---

# /skills - Skill Management Skill

This skill manages reusable instruction templates via the gobby-skills MCP server. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/skills list` - List all skills
Call `gobby-skills.list_skills` with:
- `tag`: Optional tag filter
- `limit`: Optional max results (default 20)

Returns skills with ID, name, description, and trigger pattern.

Example: `/skills list` → `list_skills()`
Example: `/skills list tag:workflow` → `list_skills(tag="workflow")`

### `/skills create <name>` - Create a new skill
Call `gobby-skills.create_skill` with:
- `name`: Skill name (used in trigger)
- `instructions`: The skill instructions
- `description`: Short description
- `trigger_pattern`: Regex pattern for when to suggest this skill
- `tags`: Optional categorization tags

Example: `/skills create code-review --instructions "Review code for..."`
→ `create_skill(name="code-review", instructions="...", trigger_pattern="/code-review|review code")`

### `/skills learn` - Learn skills from current session
Call `gobby-skills.learn_from_session` to analyze the current session and extract reusable patterns as skills.

Example: `/skills learn` → `learn_from_session()`

### `/skills export` - Export skills to CLI formats
Call `gobby-skills.export_skills` to export skills as files for:
- Claude Code (.claude/skills/)
- Codex (~/.codex/skills/)
- Gemini (~/.gemini/commands/)

Example: `/skills export` → `export_skills()`
Example: `/skills export claude` → `export_skills(format="claude")`

### `/skills show <skill-id>` - Show skill details
Call `gobby-skills.get_skill` with:
- `skill_id`: The skill ID to retrieve

Returns full skill instructions and metadata.

Example: `/skills show sk-abc123` → `get_skill(skill_id="sk-abc123")`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For list: Table with skill ID, name, trigger pattern
- For create: Confirm creation with skill ID
- For learn: Show extracted skills from session
- For export: Summary of exported files by format
- For show: Full skill instructions and metadata

## Skill Concepts

- **Trigger pattern**: Regex that suggests when to use the skill
- **Instructions**: The actual guidance injected when skill activates
- **Tags**: Categorization for filtering and organization

## Error Handling

If the subcommand is not recognized, show available subcommands:
- list, create, learn, export, show
