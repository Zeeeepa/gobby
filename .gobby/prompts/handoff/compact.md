---
description: Compact handoff summary prompt for cumulative compression
required_variables:
  - transcript_summary
  - last_messages
  - git_status
  - file_changes
optional_variables:
  - previous_summary
  - structured_context
  - git_diff_summary
---
You are creating a session continuation summary after a compaction event.
Compact summaries are for in-session continuity. Be MORE detailed than session-end summaries.
Preserve exact error messages verbatim, not paraphrases.

## Structured Session Data (extracted from tool calls):
{{ structured_context }}

Use this data to anchor your summary with specific file names, commit SHAs, and task IDs.

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

## Actual Code Changes:
{{ git_diff_summary }}

---

Create a continuation summary optimized for resuming work after compaction.
Use these sections:

### Current Focus
[Exactly what was being worked on when compaction hit: file, function, specific change.
This is the most important section. Be as specific as possible.]

### What Was Just Done
[Bullet points of this segment's actions only, not historical.
Reference specific files, functions, commit SHAs.]

### Session History (compressed)
[1-2 sentences if previous_summary exists. Skip if no previous context.]

### Technical State
- Files with uncommitted changes: [list with status]
- Recent commits: [list with SHAs and messages]
- Errors or blockers: [exact error messages if any, "None" if none]

### Immediate Next Action
[Single most important thing to do next. Must be specific enough to act on immediately
without additional context -- include file name, function name, and what to do.]

IMPORTANT: Prioritize recency. "Current Focus" and "What Was Just Done"
should be detailed and specific. Historical context should be compressed.
Use only ASCII-safe characters.
