---
name: codex-review
description: How to run Codex code reviews and adversarial reviews. Use when asked to review code with Codex, run adversarial review, or when the codex review gate blocks.
category: integration
tags:
  - gobby
metadata:
  gobby:
    audience: interactive
    depth: 0
---

# Codex Review

Run code reviews using the Codex CLI. Supports standard review and adversarial review modes.

## Standard Review

Use `codex review` for straightforward code review against local git state.

```bash
# Review uncommitted changes (staged + unstaged + untracked)
codex review --uncommitted

# Review changes against a base branch
codex review --base main

# Review a specific commit
codex review --commit <sha>

# With custom review instructions
codex review --uncommitted "Focus on error handling and edge cases"
```

## Adversarial Review

Use `codex exec` with the adversarial review prompt for deeper, skeptical analysis that challenges the change rather than validating it.

```bash
codex exec -s read-only "<adversarial review prompt>"
```

### Adversarial Review Prompt Template

Pipe the diff context and use this prompt structure:

```xml
<role>
You are Codex performing an adversarial software review.
Your job is to break confidence in the change, not to validate it.
</role>

<task>
Review the provided repository context as if you are trying to find the strongest reasons this change should not ship yet.
</task>

<operating_stance>
Default to skepticism.
Assume the change can fail in subtle, high-cost, or user-visible ways until the evidence says otherwise.
Do not give credit for good intent, partial fixes, or likely follow-up work.
If something only works on the happy path, treat that as a real weakness.
</operating_stance>

<attack_surface>
Prioritize the kinds of failures that are expensive, dangerous, or hard to detect:
- auth, permissions, tenant isolation, and trust boundaries
- data loss, corruption, duplication, and irreversible state changes
- rollback safety, retries, partial failure, and idempotency gaps
- race conditions, ordering assumptions, stale state, and re-entrancy
- empty-state, null, timeout, and degraded dependency behavior
- version skew, schema drift, migration hazards, and compatibility regressions
- observability gaps that would hide failure or make recovery harder
</attack_surface>

<review_method>
Actively try to disprove the change.
Look for violated invariants, missing guards, unhandled failure paths, and assumptions that stop being true under stress.
Trace how bad inputs, retries, concurrent actions, or partially completed operations move through the code.
</review_method>

<finding_bar>
Report only material findings.
Do not include style feedback, naming feedback, low-value cleanup, or speculative concerns without evidence.
A finding should answer:
1. What can go wrong?
2. Why is this code path vulnerable?
3. What is the likely impact?
4. What concrete change would reduce the risk?
</finding_bar>

<grounding_rules>
Be aggressive, but stay grounded.
Every finding must be defensible from the provided repository context or tool outputs.
Do not invent files, lines, code paths, incidents, attack chains, or runtime behavior you cannot support.
If a conclusion depends on an inference, state that explicitly and keep the confidence honest.
</grounding_rules>

<calibration_rules>
Prefer one strong finding over several weak ones.
Do not dilute serious issues with filler.
If the change looks safe, say so directly and return no findings.
</calibration_rules>
```

## Stop Review Gate Prompt

When the codex review gate blocks your stop, use this prompt to run the gate review:

```bash
codex exec -s read-only "<stop gate prompt with diff context>"
```

The stop gate prompt reviews only the immediately previous turn's work:

```xml
<task>
Run a stop-gate review of the previous Claude turn.
Only review code changes from the previous turn — pure status, setup, or reporting output does not count.
Challenge whether that specific work and its design choices should ship.
</task>

<compact_output_contract>
Return a compact final answer.
Your first line must be exactly one of:
- ALLOW: <short reason>
- BLOCK: <short reason>
Do not put anything before that first line.
</compact_output_contract>

<default_follow_through_policy>
Use ALLOW if the previous turn did not make code changes or if you do not see a blocking issue.
Use BLOCK only if the previous turn made code changes and you found something that still needs to be fixed.
</default_follow_through_policy>

<grounding_rules>
Ground every blocking claim in the repository context or tool outputs.
Do not treat the previous Claude response as proof that code changes happened; verify from the repository state.
</grounding_rules>

<dig_deeper_nudge>
If the previous turn did make code changes, check for second-order failures, empty-state behavior, retries, stale state, rollback risk, and design tradeoffs before you finalize.
</dig_deeper_nudge>
```

## Execution Mode

Before running a review, estimate the size:

1. Check `git status --short --untracked-files=all` and `git diff --shortstat`
2. For branch review: `git diff --shortstat <base>...HEAD`
3. Small (1-2 files): run in foreground
4. Larger or unclear: run in background via `Bash(command="...", run_in_background=true)`

## After Review

Follow the `codex-result-handling` skill guidelines:
- Present findings verbatim, ordered by severity
- **Do NOT auto-fix issues** — ask the user which findings to address
- If the review passes clean, set the gate variable if applicable:
  `set_variable(name="codex_review_gate_passed", value=true)`
