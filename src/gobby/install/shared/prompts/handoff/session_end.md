---
description: Session end handoff summary prompt
required_variables:
  - transcript_summary
  - last_messages
  - git_status
  - file_changes
optional_variables:
  - structured_context
  - git_diff_summary
---
You are generating a session summary for a future AI agent to resume work. Be precise.
Reference specific file names, function names, error messages, and commit SHAs.
Do NOT use vague phrases like "various improvements", "several fixes", "continued work on".
If no information is available for a section, say "None" rather than guessing.

## Structured Session Data (extracted from tool calls):
{{ structured_context }}

Use this data to anchor your summary with specific file names, commit SHAs, and task IDs.

## Transcript (last 100 turns):
{{ transcript_summary }}

## Last Messages:
{{ last_messages }}

## Git Status:
{{ git_status }}

## Files Changed:
{{ file_changes }}

## Actual Code Changes:
{{ git_diff_summary }}

Create a markdown summary with the following sections (do NOT include a top-level '# Session Summary' header):

## What Was Accomplished
[Bullet points referencing specific files, functions, and commits. Each bullet should name the file and describe the specific change.]

## Key Technical Decisions
[Decisions and WHY they were made. Reference specific alternatives considered. Use key_decisions from structured data above.]

## Problems Encountered
[Errors, failed approaches, exact error messages. Write "None" if none.]

## Current State
[What is working, what is broken, uncommitted changes, failing tests.]

## Files Changed
[For each file: explain the specific change using diff content. Do not just list file names.]

## Next Steps
[Numbered list. Each item must be actionable without additional context -- include file names, function names, and what specifically to do.]

Use only ASCII-safe characters - avoid Unicode em-dashes, smart quotes, or special characters.
