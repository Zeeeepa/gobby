# Production-Ready Meeseeks Workflows

## Overview

This plan documents enhancements to make the meeseeks agent workflows production-ready by integrating existing infrastructure (external LLM validation, task expansion) and fixing identified gaps from E2E testing.

## Current State

The meeseeks system consists of:
- **meeseeks:box** (orchestrator): Runs in Claude Code, finds tasks, spawns workers, reviews, merges
- **meeseeks:worker** (worker): Runs in isolated clones, claims task, implements, commits, reports, terminates

### E2E Test Results (2026-02-05)
- **meeseeks-gemini (Gemini/Ghostty)**: Pass
- **meeseeks-claude (Claude/tmux)**: Pass (after spawn executor fix)

### Identified Gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| Worktree vs clone inconsistency | Confusion, potential failures | High |
| Manual code review | Requires human intervention | High |
| No task expansion | Must create tasks manually | Medium |
| Limited error recovery | Stuck tasks after timeout | Medium |
| Sequential workers only | Slow for large task trees | Low |

## Implementation Tasks

### Task 1: Fix Isolation Consistency

**Problem:** Agent definition defaults to `clone`, orchestrator requests `worktree`.

**Files:**
- `.gobby/workflows/meeseeks-box.yaml` line 148

**Change:**
```yaml
# Before
"isolation": "worktree"

# After
"isolation": "clone"
```

**Also update:**
- Documentation strings referencing "worktree" to "clone"
- Step name `merge_worktree` to `merge_changes` (optional)
- Step name `cleanup_worktree` to `cleanup_clone` (optional)

---

### Task 2: Add validate_code_changes MCP Tool

**Problem:** No automated code review tool exists.

**Solution:** Create MCP tool that wraps existing `run_external_validation()`.

**File:** `src/gobby/mcp_proxy/tools/task_validation.py`

**Implementation:**
```python
@registry.tool(
    name="validate_code_changes",
    description="Validate code changes from a worker branch using external LLM validation."
)
async def validate_code_changes(
    task_id: str,
    branch_name: str,
    base_branch: str = "dev",
    clone_path: str | None = None,
) -> dict[str, Any]:
    """
    Run external LLM validation on branch diff.

    Args:
        task_id: Task being validated
        branch_name: Feature branch with changes
        base_branch: Branch to diff against (default: dev)
        clone_path: Path to clone directory (for reading files)

    Returns:
        {
            "valid": bool,
            "issues": [{"type": str, "severity": str, "title": str, "details": str}],
            "summary": str
        }
    """
```

**Reuse:**
- `run_external_validation()` from `src/gobby/tasks/external_validator.py`
- `ExternalValidationResult` dataclass
- `parse_issues_from_response()` from `src/gobby/tasks/issue_extraction.py`

---

### Task 3: Update code_review Step for Automation

**Problem:** User must manually set `review_approved` variable.

**File:** `.gobby/workflows/meeseeks-box.yaml`

**Changes:**

1. Update `code_review` step to call `validate_code_changes`
2. Add `on_mcp_success` handlers to auto-set variables:
```yaml
on_mcp_success:
  - server: gobby-tasks-validation
    tool: validate_code_changes
    action: set_variable
    variable: review_approved
    value: "{{ result.valid }}"
  - server: gobby-tasks-validation
    tool: validate_code_changes
    action: set_variable
    variable: review_deficiencies
    value: "{{ result.issues }}"
```

---

### Task 4: Add Task Expansion Integration

**Problem:** Must create tasks manually before running orchestrator.

**File:** `.gobby/workflows/meeseeks-box.yaml`

**Changes:**

1. Add variable:
```yaml
variables:
  auto_expand: false  # Set true to auto-expand session_task if no subtasks
```

2. Add steps before `find_work`:
```yaml
- name: check_expansion
  description: "Check if session_task needs expansion"
  transitions:
    - to: expand_task
      when: "variables.auto_expand and not task_has_subtasks(variables.session_task)"
    - to: find_work
      when: "task_has_subtasks(variables.session_task) or not variables.auto_expand"

- name: expand_task
  description: "Expand task into subtasks using LLM"
  action: call_mcp_tool
  tool_name: "gobby-tasks:execute_expansion"
  tool_args:
    task_id: "{{ variables.session_task }}"
  on_success: set_variable(expansion_successful, true)
  on_error: set_variable(expansion_failed, true)
  transitions:
    - to: find_work
      when: "variables.expansion_successful"
    - to: handle_expansion_failure
      when: "variables.expansion_failed"

- name: handle_expansion_failure
  description: "Handle failed expansion (log/notify)"
  action: call_mcp_tool
  tool_name: "gobby-tasks:log_expansion_failure"
  transitions:
    - to: find_work # Fallback to manual work finding

```

**Reuse:**
- `save_expansion_spec()` from `src/gobby/mcp_proxy/tools/tasks/_expansion.py`
- `execute_expansion()` from same file
- `/g expand` skill

---

### Task 5: Add Retry Logic to handle_timeout

**Problem:** Timeout returns to find_work without retry. Task left in `in_progress`.

**File:** `.gobby/workflows/meeseeks-box.yaml`

**Changes:**

1. Add retry tracking variables:
```yaml
variables:
  task_attempts: {}      # {task_id: attempt_count}
  max_task_retries: 3
```

2. Enhance `handle_timeout` with retry logic:
```yaml
transitions:
  - to: increment_retry_count
    when: "task_attempts.get(variables.current_task_id, 0) < variables.max_task_retries"
  - to: escalate_task
    when: "task_attempts.get(variables.current_task_id, 0) >= variables.max_task_retries"

- name: increment_retry_count
  description: "Increment retry counter for the current task"
  action: set_variable
  variable: task_attempts
  value: "{{ task_attempts | update({variables.current_task_id: task_attempts.get(variables.current_task_id, 0) + 1}) }}"
  transitions:
    - to: retry_task

- name: retry_task
  description: "Clean up failed worker and respawn"
  action: call_mcp_tool
  tool_name: "gobby-agents:kill_agent" # Kill the stuck worker
  tool_args:
    agent_id: "{{ variables.current_worker_id }}"
  transitions:
      - to: find_work # Reset and try again (find_work should re-assign or pick up)

- name: escalate_task
  description: "Escalate task for human review"
  action: call_mcp_tool
  tool_name: "gobby-tasks:mark_needs_review"
  tool_args:
    task_id: "{{ variables.current_task_id }}"
    reason: "Max retries exceeded"
  transitions:
    - to: find_work # Move on to next task

```

3. Add `retry_task` step (kill worker, reset task, respawn)
4. Add `escalate_task` step (mark for human review)

---

### Task 6: Parallel Worker Support (Future)

**Problem:** Sequential spawning - one worker at a time.

**Approach:** Create new workflow variant `meeseeks-box-parallel.yaml`.

**Deferred:** Complex changes, implement after core fixes are stable.

**Key changes needed:**
- Replace single-value vars with arrays: `active_workers: []`
- Add `monitor_workers` step polling all active workers
- Spawn up to `max_parallel_workers` before waiting
- Process completions as they arrive

---

## Verification Plan

### Unit Tests
```bash
uv run pytest tests/mcp_proxy/tools/test_task_validation.py -v -k validate_code_changes
```

### Integration Test
1. Create test task with subtask
2. Run meeseeks-claude orchestrator
3. Verify: clone isolation, worker termination, automated review, task closure

### E2E Test
```bash
cat tests/e2e/meeseeks_test_marker.py  # Check before/after
```

---

## File Summary

| File | Changes |
|------|---------|
| `.gobby/workflows/meeseeks-box.yaml` | Isolation fix, expansion steps, retry logic, code review automation |
| `src/gobby/mcp_proxy/tools/task_validation.py` | Add `validate_code_changes` tool |
| `.gobby/agents/meeseeks.yaml` | Documentation updates (optional) |
| `.gobby/agents/meeseeks-claude.yaml` | Documentation updates (optional) |

## Dependencies (Reuse)

- `src/gobby/tasks/external_validator.py` - `run_external_validation()`
- `src/gobby/mcp_proxy/tools/tasks/_expansion.py` - `save_expansion_spec()`, `execute_expansion()`
- `src/gobby/tasks/issue_extraction.py` - `parse_issues_from_response()`

## Notes

- External validation supports 3 modes: `llm`, `agent`, `spawn` - use `llm` for code review (fastest)
- Task expansion has resume capability - survives session compaction
- Clone isolation preferred over worktree (simpler, better sandbox compatibility)
- All changes maintain backward compatibility with existing workflows
