---
description: Extract reusable memories from session transcripts
required_variables:
  - transcript_summary
  - project_name
optional_variables:
  - task_refs
  - files
  - tool_summary
  - min_importance
  - max_memories
defaults:
  min_importance: 0.8
  max_memories: 3
---
Analyze this coding session and extract ONLY memories that would save >5 minutes of future discovery work.

## Session Context
- Project: {{ project_name }}
{% if task_refs %}- Tasks worked: {{ task_refs }}{% endif %}
{% if files %}- Files modified: {{ files }}{% endif %}
{% if tool_summary %}- Key tool actions: {{ tool_summary }}{% endif %}

## Session Transcript
{{ transcript_summary }}

## HIGH-VALUE memories (extract these):
- **Undocumented behaviors**: Bugs, limitations, workarounds not in docs
- **Root cause analysis**: Debugging insights that would take time to rediscover
- **Format specifications**: Required formats, schemas, or conventions with examples
- **API gotchas**: Parameter quirks, error codes, required fields
- **Quantified metrics**: Specific numbers (coverage %, file counts, gaps)
- **Complex architecture**: Multi-step workflows, module relationships

## LOW-VALUE memories (DO NOT extract):
- Generic Python/git/programming practices (Pydantic, pre-commit, dataclasses)
- Obvious code organization visible from file structure
- Vague observations with "may", "likely", "should be" (only concrete facts)
- Information discoverable in <30 seconds from reading code or docs
- Plan file locations or temporary session state
- Standard tool usage patterns (commit formats, CLI commands)
- Anything already stated in CLAUDE.md, README, or docstrings

## The 5-Minute Rule
Before including a memory, ask: "Would finding this information take an agent >5 minutes?"
- YES → Include it (e.g., "Claude Code doesn't return tool_result in post-tool-use hooks")
- NO → Skip it (e.g., "The project uses pre-commit hooks for formatting")

## Output Format
```json
[
  {
    "content": "Specific, actionable knowledge (1-3 sentences with concrete details)",
    "memory_type": "fact | pattern | preference | context",
    "importance": 0.85,
    "tags": ["relevant", "tags"]
  }
]
```

Guidelines:
- Only include memories with importance >= {{ min_importance | default(0.8) }}
- Maximum {{ max_memories | default(3) }} memories per session
- Most sessions should return an empty array: []
- importance: 0.8 = valuable, 0.9 = critical, 1.0 = essential (no 0.7 memories)
- When in doubt, don't extract - fewer high-quality memories > many low-quality ones
