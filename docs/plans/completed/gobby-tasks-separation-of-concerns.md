# Audit: gobby-tasks Server — Separation of Concerns

**Task:** #7341
**Date:** 2026-02-09
**Status:** Research complete

---

## 1. Current State: 53 Tools on One Server

The `gobby-tasks` MCP server currently exposes **53 tools**, assembled from **13 sub-registries** via `tasks/_factory.py`. A 14th sub-registry (GitHub sync, 6 tools) exists in code but is never registered because `mcp_manager` is not passed from `registries.py`.

### Tool Inventory by Sub-Registry

| # | Sub-Registry | Source File | Tools | Count |
|---|---|---|---|---|
| 1 | **CRUD** | `tasks/_crud.py` | `create_task`, `get_task`, `update_task`, `list_tasks` | 4 |
| 2 | **Lifecycle** | `tasks/_lifecycle.py` | `close_task`, `reopen_task`, `delete_task`, `add_label`, `remove_label`, `claim_task`, `mark_task_for_review` | 7 |
| 3 | **Session** | `tasks/_session.py` | `link_task_to_session`, `get_session_tasks`, `get_task_sessions` | 3 |
| 4 | **Search** | `tasks/_search.py` | `search_tasks`, `reindex_tasks` | 2 |
| 5 | **Expansion** | `tasks/_expansion.py` | `save_expansion_spec`, `execute_expansion`, `get_expansion_spec` | 3 |
| 6 | **Validation** | `task_validation.py` | `validate_task`, `get_validation_status`, `reset_validation_count`, `get_validation_history`, `get_recurring_issues`, `clear_validation_history`, `de_escalate_task`, `generate_validation_criteria`, `run_fix_attempt`, `validate_and_fix` | 10 |
| 7 | **Dependencies** | `task_dependencies.py` | `add_dependency`, `remove_dependency`, `get_dependency_tree`, `check_dependency_cycles` | 4 |
| 8 | **Readiness** | `task_readiness.py` | `list_ready_tasks`, `list_blocked_tasks`, `suggest_next_task` | 3 |
| 9 | **Sync** | `task_sync.py` | `sync_tasks`, `get_sync_status`, `link_commit`, `unlink_commit`, `auto_link_commits`, `get_task_diff` | 6 |
| 10 | **Orchestrate** | `orchestration/orchestrate.py` | `orchestrate_ready_tasks` | 1 |
| 11 | **Monitor** | `orchestration/monitor.py` | `get_orchestration_status`, `poll_agent_status` | 2 |
| 12 | **Review** | `orchestration/review.py` | `spawn_review_agent`, `process_completed_agents` | 2 |
| 13 | **Cleanup** | `orchestration/cleanup.py` | `approve_and_cleanup`, `cleanup_reviewed_worktrees`, `cleanup_stale_worktrees` | 3 |
| 14 | **Wait** | `orchestration/wait.py` | `wait_for_task`, `wait_for_any_task`, `wait_for_all_tasks` | 3 |
| — | **GitHub Sync** *(unregistered)* | `task_github.py` | `import_github_issues`, `sync_task_to_github`, `create_pr_for_task`, `link_github_repo`, `unlink_github_repo`, `get_github_status` | 6 |
| | | | **Total (registered)** | **53** |

---

## 2. Domain Categorization

Grouping the 53 tools by their actual domain concern (not their current registry):

### A. Core Task Management (16 tools)
Tools that operate on task entities directly — CRUD, lifecycle, labels, session links, search.

| Tool | Why it belongs |
|---|---|
| `create_task`, `get_task`, `update_task`, `list_tasks` | Entity CRUD |
| `close_task`, `reopen_task`, `delete_task` | Status transitions |
| `add_label`, `remove_label` | Task metadata |
| `claim_task`, `mark_task_for_review` | Assignment/status |
| `link_task_to_session`, `get_session_tasks`, `get_task_sessions` | Session binding |
| `search_tasks`, `reindex_tasks` | Discovery |

**Verdict:** These are the natural core of `gobby-tasks`. They have minimal external dependencies (just `LocalTaskManager`, `TaskSyncManager`).

### B. Task Expansion (3 tools)
| Tool | Concern |
|---|---|
| `save_expansion_spec` | Persist decomposition plan |
| `execute_expansion` | Create subtasks atomically |
| `get_expansion_spec` | Resume after compaction |

**Verdict:** Tightly coupled to task entity (creates subtasks). Belongs on `gobby-tasks`.

### C. Task Dependencies & Readiness (7 tools)
| Tool | Concern |
|---|---|
| `add_dependency`, `remove_dependency` | Relationship CRUD |
| `get_dependency_tree`, `check_dependency_cycles` | Graph queries |
| `list_ready_tasks`, `list_blocked_tasks` | Readiness queries |
| `suggest_next_task` | AI-powered prioritization |

**Verdict:** Dependencies are a structural property of tasks. Readiness is a query over dependencies. These belong on `gobby-tasks`.

### D. Task Validation (10 tools)
| Tool | Concern |
|---|---|
| `validate_task` | Run validation checks |
| `get_validation_status`, `get_validation_history` | Query validation state |
| `get_recurring_issues` | Analyze failure patterns |
| `reset_validation_count`, `clear_validation_history` | Reset state |
| `de_escalate_task` | Return from escalation |
| `generate_validation_criteria` | AI-generate criteria |
| `run_fix_attempt` | **Spawn fix agent** |
| `validate_and_fix` | **Compound: validate + spawn fix + re-validate** |

**Verdict: Mixed concern.** The first 7 tools are task-centric (query/update validation state on the task entity). But `run_fix_attempt` and `validate_and_fix` spawn agents — they're orchestration in disguise. `generate_validation_criteria` calls LLM. This registry mixes data access with workflow execution.

### E. Task Sync & Commits (6 tools)
| Tool | Concern |
|---|---|
| `sync_tasks` | Git ↔ JSONL sync |
| `get_sync_status` | Sync state query |
| `link_commit`, `unlink_commit` | Commit ↔ task binding |
| `auto_link_commits` | Auto-detect commit references |
| `get_task_diff` | Combined diff for task commits |

**Verdict:** Git/commit integration is a distinct concern from task CRUD, but these tools operate on task entities. Could stay or go.

### F. Orchestration (11 tools)
| Tool | Concern |
|---|---|
| `orchestrate_ready_tasks` | **Spawn agents in worktrees** |
| `get_orchestration_status` | Query agent lifecycle state |
| `poll_agent_status` | **Poll agent completion** |
| `spawn_review_agent` | **Spawn review agent** |
| `process_completed_agents` | **Route agents to review/cleanup** |
| `approve_and_cleanup` | **Close task + delete worktree** |
| `cleanup_reviewed_worktrees` | **Merge branches + delete worktrees** |
| `cleanup_stale_worktrees` | **Delete inactive worktrees** |
| `wait_for_task` | Block until task completes |
| `wait_for_any_task` | Block until any task completes |
| `wait_for_all_tasks` | Block until all tasks complete |

**Verdict: Clear separation of concerns violation.** These tools:
- Depend on `AgentRunner`, `LocalWorktreeManager`, `WorktreeGitManager` — not task-centric
- Manage agent lifecycle, not task lifecycle
- Are conditionally registered (only when `worktree_storage is not None`)
- Already have their own internal registry named `"gobby-orchestration"`
- Are only used by the meeseeks-box workflow and auto-orchestrator patterns

---

## 3. Unused or Redundant Tools

### Potentially Redundant
| Tool | Overlap | Assessment |
|---|---|---|
| `validate_and_fix` | Compound of `validate_task` + `run_fix_attempt` | **Keep** — convenience compound for single-call validation loops. Different use case (automated vs. manual). |
| `list_ready_tasks` vs `suggest_next_task` | Both find available work | **Keep both** — `list_ready_tasks` is a data query, `suggest_next_task` adds AI prioritization. |
| `cleanup_reviewed_worktrees` vs `cleanup_stale_worktrees` | Both delete worktrees | **Keep both** — different selection criteria (reviewed vs. stale by time). |

### Dead Code: GitHub Sync (6 tools)
The `create_github_sync_registry` function exists in `task_github.py` but `mcp_manager` is never passed from `registries.py:113-123`. These 6 tools are **never registered**:
- `import_github_issues`, `sync_task_to_github`, `create_pr_for_task`, `link_github_repo`, `unlink_github_repo`, `get_github_status`

**Action:** Either wire up `mcp_manager` in `registries.py` or document this as intentionally deferred.

### Low-Value Tools
| Tool | Usage | Assessment |
|---|---|---|
| `reindex_tasks` | Manual TF-IDF rebuild | Rarely needed. Keep as admin escape hatch. |
| `check_dependency_cycles` | Diagnostic | Rarely called directly. Keep for debugging. |

---

## 4. Proposed Server Distribution

### Recommendation: Extract `gobby-orchestration` (Option A)

Move the 11 orchestration tools to their own server. This is the highest-impact, lowest-risk change.

**Before:**
```
gobby-tasks: 53 tools (everything)
```

**After:**
```
gobby-tasks:          42 tools (core tasks + validation + deps + sync)
gobby-orchestration:  11 tools (agent spawning, monitoring, cleanup, wait)
```

#### Why Only Orchestration?

1. **Clearest domain boundary.** Orchestration tools manage agents and worktrees, not tasks. They depend on `AgentRunner`, `WorktreeGitManager`, `LocalWorktreeManager` — none of which are task concerns.

2. **Already architecturally separate.** The code already has `create_orchestration_registry()` returning a registry named `"gobby-orchestration"`. The factory just merges it.

3. **Conditionally registered.** Orchestration tools only register when `worktree_storage is not None`, proving they're optional for the task server.

4. **Single consumer.** Only the meeseeks-box workflow (and its deprecated predecessor) use orchestration tools. Migration scope is narrow.

5. **Progressive disclosure benefit.** Agents doing basic task work (create, claim, close) never need to see orchestration tools. 42 tools in `list_tools` is better than 53.

#### Why NOT Extract Validation?

Validation tools (10) are tempting to extract but:
- They operate on task entity fields (`validation_status`, `validation_feedback`, `validation_fail_count`)
- `validate_task` and `close_task` are commonly called together
- `run_fix_attempt` spawns agents but always in service of a specific task
- Splitting would force agents to call two servers for the common "validate then close" flow
- 42 tools is already a meaningful reduction from 53

Validation could be extracted in a future pass if the server grows again.

### Alternative: More Aggressive Split (Option B)

If 42 is still too many:

```
gobby-tasks:          26 tools (core + deps + readiness + expansion)
gobby-validation:     10 tools (validation domain)
gobby-sync:            6 tools (git sync + commits)
gobby-orchestration:  11 tools (agent lifecycle)
```

**Tradeoff:** More servers = more progressive disclosure overhead. Each agent session must call `list_tools` per server. Option B trades tool count per server for server count.

---

## 5. Migration Risk Assessment

### What References `gobby-tasks` + Orchestration Tools?

| Location | Tools Referenced | Impact |
|---|---|---|
| `meeseeks-box.yaml` | `wait_for_task`, `suggest_next_task`, `get_task` | **Must update** server name for `wait_for_task` |
| `auto-task-claude.yaml` (deprecated) | `wait_for_task` | Low priority, deprecated |
| `meeseeks-box-pipeline.yaml` | Uses CLI (`gobby task wait`), not MCP | **No impact** — CLI routes through task_manager |
| `session-lifecycle.yaml` | Governance rules only, no direct tool calls | **No impact** |
| `skills/tasks/SKILL.md` | `suggest_next_task` documentation | Update docs |
| `instructions.py` | General progressive disclosure | **No impact** |

### Migration Steps

1. **Create `gobby-orchestration` registry** in `registries.py` (it already exists as a sub-registry, just needs to be registered as a top-level server)
2. **Remove orchestration merge** from `tasks/_factory.py:147-157`
3. **Update `meeseeks-box.yaml`** to call `gobby-orchestration` instead of `gobby-tasks` for orchestration tools
4. **Update deprecated `auto-task-claude.yaml`** or leave as-is (it's deprecated)
5. **Update skill documentation** if it references orchestration tools on `gobby-tasks`
6. **Test:** Verify `list_tools("gobby-orchestration")` returns 11 tools, `list_tools("gobby-tasks")` returns 42

### Risk Level: **Low**

- The orchestration registry already exists (`create_orchestration_registry` in `task_orchestration.py`)
- Only 1 active workflow file needs updating
- No agent definitions reference orchestration tools by server name (they use workflow actions)
- The meeseeks-box pipeline uses CLI commands, not MCP tools

---

## 6. Summary

| Finding | Action |
|---|---|
| 11 orchestration tools violate separation of concerns | **Extract to `gobby-orchestration` server** |
| 10 validation tools are borderline but task-centric | **Keep on `gobby-tasks` for now** |
| 6 GitHub sync tools exist but are never registered | **Wire up or document as deferred** |
| No truly redundant tools found | No tools to remove |
| Migration risk is low (1 active workflow to update) | Safe to proceed |

### Recommended Next Steps

1. Create implementation task: Extract orchestration tools to `gobby-orchestration`
2. Create bug task: GitHub sync tools never registered (missing `mcp_manager` in `registries.py`)
3. Optional future: Re-evaluate validation extraction after orchestration is done
