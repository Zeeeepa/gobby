# Enable Rules Incrementally

## Context
Session-lifecycle workflow is soft-deleted. Progressive disclosure rules (3 tracking + 3 blocking) already work. 12 session-default init rules just synced. Now we need to enable the remaining 54 disabled rules that replace session-lifecycle behaviors.

## Strategy: Enable by Risk Tier

### Tier 1: Safe After-Tool Tracking (no user-facing behavior change)
These just track state — no blocking, no context injection.

| Rule | File | What it does |
|------|------|-------------|
| `clear-tool-block-on-tool` | stop-gates.yaml | Reset `_tool_block_pending` after any tool |
| `reset-stop-on-native-tool` | stop-gates.yaml | Reset `stop_attempts` on non-MCP tool |
| `track-pending-memory-review` | tool-hygiene.yaml | Set `pending_memory_review` after edits/close |
| `track-task-claim` | task-enforcement.yaml | Track `task_claimed`/`claimed_task_id` after claim |
| `track-task-release` | task-enforcement.yaml | Clear task tracking after close/reopen |

### Tier 2: Plan Mode Detection
| Rule | File | What it does |
|------|------|-------------|
| `set-mode-level-on-enter` | plan-mode.yaml | Set `mode_level=0` after EnterPlanMode |
| `restore-mode-level-on-exit` | plan-mode.yaml | Restore mode_level after ExitPlanMode |
| `detect-plan-mode-enter` | plan-mode.yaml | Additional plan mode enter tracking |
| `detect-plan-mode-exit` | plan-mode.yaml | Additional plan mode exit tracking |

### Tier 3: Before-Agent Resets
| Rule | File | What it does |
|------|------|-------------|
| `clear-tool-block-on-prompt` | stop-gates.yaml | Reset `_tool_block_pending` on new prompt |
| `reset-error-triage-on-prompt` | stop-gates.yaml | Reset `pre_existing_errors_triaged` on new prompt |

### Tier 4: Before-Tool Blocking (user-visible enforcement)
| Rule | File | What it does |
|------|------|-------------|
| `block-native-task-tools` | task-enforcement.yaml | Block CC native task tools |
| `require-task-before-edit` | task-enforcement.yaml | Block Edit/Write without claimed task |
| `require-uv` | tool-hygiene.yaml | Block bare python/pip |
| `require-commit-before-close` | task-enforcement.yaml | Block close_task without commit |
| `block-skip-validation-with-commit` | task-enforcement.yaml | Block skip_validation with commit |
| `block-ask-during-stop-compliance` | task-enforcement.yaml | Block AskUserQuestion during stop |
| `require-task` | task-enforcement.yaml | Generic task requirement |
| `require-tests-pass` | task-enforcement.yaml | Block without passing tests |

### Tier 5: Stop Gates (most impactful)
| Rule | File | What it does |
|------|------|-------------|
| `increment-stop-attempts` | stop-gates.yaml | Increment counter on stop |
| `block-stop-after-tool-block` | stop-gates.yaml | Block stop after tool block |
| `require-error-triage` | stop-gates.yaml | Block stop without error triage |
| `memory-review-gate` | stop-gates.yaml | Block stop pending memory review |
| `require-task-close` | stop-gates.yaml | Block stop with unclosed task |
| `guide-task-continuation` | auto-task.yaml | Guide subtask continuation |

### Tier 6: Session Lifecycle (inject_context, mcp_call — need backend verification)
| Rule | File | Type |
|------|------|------|
| `inject-previous-session-summary` | context-handoff.yaml | inject_context |
| `inject-compact-handoff` | context-handoff.yaml | inject_context |
| `inject-skills-on-start` | context-handoff.yaml | inject_context |
| `inject-task-context-on-start` | context-handoff.yaml | inject_context |
| `inject-error-triage-policy` | context-handoff.yaml | inject_context |
| `reset-plan-mode-on-session-start` | plan-mode.yaml | set_variable |
| `clear-pending-context-reset-on-start` | context-handoff.yaml | set_variable |
| `capture-baseline-dirty-files-on-start` | context-handoff.yaml | mcp_call |
| `memory-sync-import` | memory-lifecycle.yaml | mcp_call |
| `task-sync-import-on-start` | context-handoff.yaml | mcp_call |
| `reset-memory-tracking-on-start` | memory-lifecycle.yaml | set_variable |
| `memory-recall-on-prompt` | memory-lifecycle.yaml | mcp_call |
| `memory-background-digest` | memory-lifecycle.yaml | mcp_call |
| `memory-capture-nudge` | memory-lifecycle.yaml | inject_context |
| `suggest-memory-after-close` | memory-lifecycle.yaml | inject_context |

### Tier 7: Session End / Pre-Compact (mcp_call heavy)
| Rule | File | Type |
|------|------|------|
| `generate-handoff-on-end` | context-handoff.yaml | mcp_call |
| `memory-extraction-on-end` | memory-lifecycle.yaml | mcp_call |
| `memory-sync-export-on-end` | memory-lifecycle.yaml | mcp_call |
| `task-sync-export-on-end` | context-handoff.yaml | mcp_call |
| `extract-handoff-context-on-compact` | context-handoff.yaml | mcp_call |
| `generate-handoff-on-compact` | context-handoff.yaml | mcp_call |
| `memory-extraction-on-compact` | memory-lifecycle.yaml | mcp_call |
| `memory-sync-export-on-compact` | memory-lifecycle.yaml | mcp_call |
| `task-sync-export-on-compact` | context-handoff.yaml | mcp_call |
| `set-pending-context-reset-on-compact` | context-handoff.yaml | set_variable |
| `reset-memory-tracking-on-compact` | memory-lifecycle.yaml | set_variable |

## Approach
Enable one tier at a time. Verify each tier before moving to next.
Tiers 1-5 are pure rule engine — safe to enable.
Tiers 6-7 use `mcp_call` and `inject_context` — need to verify the rule engine dispatches these correctly.
