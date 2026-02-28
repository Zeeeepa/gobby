---
description: Generate compact handoff context and archival summary from session digest
required_variables:
  - digest_markdown
---
Given a session's complete turn-by-turn digest, produce two outputs separated by the exact markers shown below.

## Session Digest
{{ digest_markdown }}

---

## Output A: Handoff Context
What the next session needs to know to continue this work.
Include: current state, open problems, key decisions, relevant file paths.
Exclude: anything the CLI's own compaction already preserves.
Keep under 500 words.

===SECTION_BREAK===

## Output B: Session Summary
Archival summary of what was accomplished.
Include: goals, outcomes, commits, tasks closed, key findings.
Keep under 800 words.
