---
description: Generate a concise description for a skill from its SKILL.md content
required_variables:
  - slug
  - snippet
---
Generate a concise 1-sentence description (max 100 chars) for this skill.

Skill name: {{ slug }}

SKILL.md content:
{{ snippet }}

Output ONLY the description text, no quotes, no explanation, no preamble.
