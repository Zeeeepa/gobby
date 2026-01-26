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
  min_importance: 0.7
  max_memories: 5
---
Analyze this coding session and extract ONLY high-value, reusable memories.

## Session Context
- Project: {{ project_name }}
{% if task_refs %}- Tasks worked: {{ task_refs }}{% endif %}
{% if files %}- Files modified: {{ files }}{% endif %}
{% if tool_summary %}- Key tool actions: {{ tool_summary }}{% endif %}

## Session Transcript
{{ transcript_summary }}

## Extract memories that are:
- **FACTS**: Project architecture, technology choices, API patterns, file locations
- **PATTERNS**: Code conventions, testing approaches, file organization, naming conventions
- **PREFERENCES**: User-stated preferences about style, approach, or tools
- **CONTEXT**: Important background that helps future work on this project

## DO NOT extract:
- Temporary debugging information
- Session-specific state that won't apply later
- Obvious/generic programming knowledge
- Information already documented in the codebase
- Duplicate information from previous memories

## Output Format
Return a JSON array of memories. Each memory should be:
- Self-contained and understandable without session context
- Specific to this project (not generic programming advice)
- Actionable or informative for future sessions

```json
[
  {
    "content": "The reusable knowledge (1-3 sentences, specific and actionable)",
    "memory_type": "fact | pattern | preference | context",
    "importance": 0.7,
    "tags": ["relevant", "tags"]
  }
]
```

Guidelines:
- Only include memories with importance >= {{ min_importance | default(0.7) }}
- Maximum {{ max_memories | default(5) }} memories
- If nothing worth remembering, return an empty array: []
- importance scale: 0.7 = useful, 0.8 = valuable, 0.9 = critical, 1.0 = essential
