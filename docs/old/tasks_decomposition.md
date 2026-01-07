# tasks.py Decomposition Analysis

**File:** `src/gobby/mcp_proxy/tools/tasks.py`
**Total Lines:** 2,391
**Analysis Date:** 2026-01-06
**Task:** gt-a5db77

## Executive Summary

The file contains 8 functional domains wrapped in a single factory function `create_task_registry()`. The Strangler Fig approach will extract domains into focused modules while keeping the registry as a facade.

## Current Structure

```
Line 1-90:     Module header, imports, constants (90 lines)
Line 92-2391:  create_task_registry() factory function (2,299 lines)
```

### Functional Domains Within create_task_registry()

| Domain | Line Range | Lines | Functions | Priority |
|--------|-----------|-------|-----------|----------|
| Expansion | 144-1104 | ~960 | 4 | HIGH |
| Validation | 268-759 | ~490 | 10 | HIGH |
| Task CRUD | 1192-1927 | ~735 | 9 | KEEP (core) |
| Dependencies | 1929-2025 | ~96 | 4 | MEDIUM |
| Readiness | 2027-2118 | ~91 | 2 | MEDIUM |
| Session Integration | 2120-2195 | ~75 | 3 | LOW |
| Git Sync | 2197-2236 | ~39 | 2 | LOW |
| Commit Linking | 2238-2391 | ~153 | 4 | MEDIUM |

## Detailed Function Mapping

### 1. Expansion Tools (~960 lines) → `task_expansion.py`

| Function | Lines | Description |
|----------|-------|-------------|
| `expand_task` | 148-266 | Expand task into subtasks via AI |
| `analyze_complexity` | 700-759 | Analyze task complexity |
| `expand_all` | 761-833 | Expand multiple unexpanded tasks |
| `expand_from_spec` | 835-999 | Create tasks from spec file |
| `expand_from_prompt` | 1001-1104 | Create tasks from user prompt |

**Dependencies:**
- `task_expander: TaskExpander` (required)
- `task_manager: LocalTaskManager`
- `dep_manager: TaskDependencyManager`
- `task_validator: TaskValidator` (optional, for auto-generating criteria)
- `project_manager: LocalProjectManager`
- Config: `auto_generate_on_expand`

### 2. Validation Tools (~490 lines) → `task_validation.py`

| Function | Lines | Description |
|----------|-------|-------------|
| `validate_task` | 268-407 | Validate task completion |
| `get_validation_status` | 409-434 | Get validation details |
| `reset_validation_count` | 436-459 | Reset failure count |
| `get_validation_history` | 461-502 | Get full history |
| `get_recurring_issues` | 504-541 | Analyze recurring issues |
| `clear_validation_history` | 543-582 | Clear history |
| `de_escalate_task` | 584-630 | Return escalated task to open |
| `generate_validation_criteria` | 632-694 | Generate criteria via AI |

**Dependencies:**
- `task_validator: TaskValidator` (required)
- `task_manager: LocalTaskManager`
- `validation_history_manager: ValidationHistoryManager`
- `get_project_repo_path()` helper

### 3. Task CRUD (~735 lines) → KEEP in `tasks.py`

| Function | Lines | Description |
|----------|-------|-------------|
| `create_task` | 1194-1350 | Create new task |
| `get_task` | 1352-1382 | Get task with dependencies |
| `update_task` | 1384-1494 | Update task fields |
| `add_label` | 1496-1516 | Add label to task |
| `remove_label` | 1518-1538 | Remove label from task |
| `close_task` | 1540-1774 | Close task with validation |
| `reopen_task` | 1776-1823 | Reopen closed task |
| `delete_task` | 1825-1848 | Delete task |
| `list_tasks` | 1850-1927 | List tasks with filters |

**Note:** `close_task` is tightly coupled with validation. Consider extracting validation logic to a separate function that `close_task` calls.

### 4. Dependencies (~96 lines) → `task_dependencies.py`

| Function | Lines | Description |
|----------|-------|-------------|
| `add_dependency` | 1931-1965 | Add dependency between tasks |
| `remove_dependency` | 1967-1984 | Remove dependency |
| `get_dependency_tree` | 1986-2011 | Get dependency tree |
| `check_dependency_cycles` | 2013-2025 | Detect cycles |

**Dependencies:**
- `dep_manager: TaskDependencyManager`

### 5. Readiness Tools (~91 lines) → `task_readiness.py`

| Function | Lines | Description |
|----------|-------|-------------|
| `list_ready_tasks` | 2029-2081 | List unblocked tasks |
| `list_blocked_tasks` | 2083-2118 | List blocked tasks |
| `suggest_next_task` | 1106-1185 | Suggest best next task |

**Dependencies:**
- `task_manager: LocalTaskManager`
- `get_current_project_id()` helper

### 6. Session Integration (~75 lines) → Could merge with sync

| Function | Lines | Description |
|----------|-------|-------------|
| `link_task_to_session` | 2122-2158 | Link task to session |
| `get_session_tasks` | 2160-2176 | Get session's tasks |
| `get_task_sessions` | 2178-2195 | Get task's sessions |

**Dependencies:**
- `session_task_manager: SessionTaskManager`

### 7. Git Sync + Commit Linking (~192 lines) → `task_sync.py`

| Function | Lines | Description |
|----------|-------|-------------|
| `sync_tasks` | 2198-2225 | Trigger sync |
| `get_sync_status` | 2227-2236 | Get sync status |
| `link_commit` | 2241-2267 | Link commit to task |
| `unlink_commit` | 2269-2295 | Unlink commit |
| `auto_link_commits` | 2297-2343 | Auto-detect and link |
| `get_task_diff_tool` | 2345-2388 | Get combined diff |

**Dependencies:**
- `sync_manager: TaskSyncManager`
- `task_manager: LocalTaskManager`
- `project_manager: LocalProjectManager`

## Shared Dependencies (Coupling Points)

### Manager Instances (created in factory)
```python
dep_manager = TaskDependencyManager(task_manager.db)          # Line 1188
session_task_manager = SessionTaskManager(task_manager.db)    # Line 1189
validation_history_manager = ValidationHistoryManager(task_manager.db)  # Line 1190
```

### Helper Functions (defined in factory)
```python
get_project_repo_path(project_id)    # Lines 129-134
get_current_project_id()             # Lines 136-142
```

### Module-Level Helper
```python
_infer_test_strategy(title, description)  # Lines 78-89
```

### Config Dependencies
```python
show_result_on_create      # From config.get_gobby_tasks_config()
auto_generate_on_create    # From validation config
auto_generate_on_expand    # From validation config
```

## Extraction Plan

### Phase 1: Create modules with delegation (Week 1)

```
mcp_proxy/tools/
├── tasks.py                    # Becomes facade (CRUD + delegation)
├── tasks_validation.py         # Extracted: validation tools
├── tasks_expansion.py          # Extracted: expansion tools
├── tasks_dependencies.py       # Extracted: dependency management
├── tasks_readiness.py          # Extracted: ready work + suggestions
└── tasks_sync.py               # Extracted: git sync + commits + sessions
```

### Extraction Order (least → most coupled)

1. **tasks_dependencies.py** (~100 lines)
   - Reason: Self-contained, only uses `dep_manager`
   - Risk: LOW

2. **tasks_sync.py** (~190 lines, including session integration)
   - Reason: Clear boundaries, minimal coupling
   - Risk: LOW

3. **tasks_readiness.py** (~170 lines, including suggest_next_task)
   - Reason: Read-only operations, uses task_manager
   - Risk: LOW

4. **tasks_validation.py** (~490 lines)
   - Reason: Complex but well-bounded
   - Challenge: `close_task` calls validation internally
   - Risk: MEDIUM

5. **tasks_expansion.py** (~960 lines)
   - Reason: Largest domain, some coupling with validation
   - Challenge: Creates dependencies, may call validation
   - Risk: MEDIUM

### Phase 2: Refactor tasks.py (~500 lines target)

- Keep CRUD operations in `tasks.py`
- Extract validation logic from `close_task` to callable function
- Re-export tools from submodules for backwards compatibility

### Phase 3: Update imports (gradual)

- MCP proxy registration continues importing from `tasks.py`
- Internal code can import from specific modules
- Remove re-exports once all callers migrated

## Circular Dependency Risks

| Risk | Modules Involved | Mitigation |
|------|-----------------|------------|
| HIGH | expansion ↔ validation | Auto-generate criteria during expand calls validation. Extract criteria generation to shared utility. |
| MEDIUM | CRUD ↔ validation | `close_task` validates. Keep validation callable, import into CRUD. |
| LOW | expansion → dependencies | One-way dependency, safe |

### Mitigation Strategy

1. **Shared utilities module**: `task_utils.py`
   - `get_project_repo_path()`
   - `get_current_project_id()`
   - `_infer_test_strategy()`
   - Config getters

2. **Validation as callable**: Make `validate_task_completion()` a standalone function that can be imported anywhere

3. **Lazy imports**: Where circular risk exists, use function-level imports

## Estimated Line Counts After Extraction

| Module | Lines | Status |
|--------|-------|--------|
| tasks.py | ~500 | Core CRUD |
| tasks_validation.py | ~350 | Extracted |
| tasks_expansion.py | ~600 | Extracted |
| tasks_dependencies.py | ~100 | Extracted |
| tasks_readiness.py | ~150 | Extracted |
| tasks_sync.py | ~200 | Extracted |
| task_utils.py | ~50 | New (shared) |
| **TOTAL** | ~1,950 | -18% reduction |

## Success Criteria

- [ ] All existing tests pass after each extraction
- [ ] No file exceeds 600 lines
- [ ] No circular imports at module level
- [ ] MCP tool registration continues working
- [ ] Each module has single clear responsibility
