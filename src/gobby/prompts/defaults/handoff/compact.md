---
description: Compact handoff summary prompt for cumulative compression
required_variables:
  - transcript_summary
  - last_messages
  - git_status
  - file_changes
optional_variables:
  - previous_summary
  - todo_list
---
You are creating a session continuation summary after a compaction event.

## Context from Earlier in This Session (if any):
{{ previous_summary }}

If there is previous context above, focus your summary on what happened AFTER
that point. Compress the historical context into a brief "Session History" section.
If no previous context, this is the first segment - summarize the full session.

## Current Transcript:
{{ transcript_summary }}

## Last Messages:
{{ last_messages }}

## Git Status:
{{ git_status }}

## Files Changed:
{{ file_changes }}

{{ todo_list }}

---

Create a continuation summary optimized for resuming work after compaction.
Use these sections:

### Current Focus
[What is being actively worked on RIGHT NOW - be specific and detailed.
This is the most important section.]

### This Segment's Progress
[Bullet points of what was accomplished in this segment]

### Session History
[1-2 sentences summarizing the overall session journey. Include if there was
previous context, otherwise skip this section.]

### Technical State
- Key files modified: [list files]
- Git status: [uncommitted changes summary]
- Any blockers or pending items

### Next Steps
[Numbered list of concrete actions to take when resuming]

IMPORTANT: Prioritize recency. "Current Focus" and "This Segment's Progress"
should be detailed and specific. Historical context should be compressed.
Use only ASCII-safe characters.
