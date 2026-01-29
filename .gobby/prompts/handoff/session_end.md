---
description: Session end handoff summary prompt
required_variables:
  - transcript_summary
  - last_messages
  - git_status
  - file_changes
optional_variables:
  - todo_list
---
Analyze this Claude Code session transcript and create a comprehensive session summary.

## Transcript (last 50 turns):
{{ transcript_summary }}

## Last Messages:
{{ last_messages }}

## Git Status:
{{ git_status }}

## Files Changed:
{{ file_changes }}

Create a markdown summary with the following sections (do NOT include a top-level '# Session Summary' header):

## Overview
[1-2 paragraph summary of what was accomplished in this session]

## Key Decisions
[List of important technical or architectural decisions made, with bullet points]

## Important Lessons Learned
[Technical insights, gotchas, or patterns discovered, with bullet points]

## Substantive Interrupts
[Times when the user changed direction significantly - NOT simple "continue" or "resume" prompts]

## Research & Epiphanies
[Key discoveries from research or debugging that should be remembered, with bullet points]

## Files Changed
[List {{ file_changes }} with specific details about WHY each file was changed and WHAT the changes accomplish.]

## Git Status
```
{{ git_status }}
```

{% if todo_list %}
{{ todo_list }}
{% endif %}

## Next Steps
[Concrete, numbered suggestions for what to do when resuming work. Be specific and actionable.]

Focus on actionable insights and context that would be valuable when resuming work later.
Use only ASCII-safe characters - avoid Unicode em-dashes, smart quotes, or special characters.
