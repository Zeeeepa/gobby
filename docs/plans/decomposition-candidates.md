# Decomposition Candidates Analysis

Based on a scan of the codebase, here are the top candidates for decomposition using the Strangler Fig pattern.

## 1. [COMPLETED] Top Candidate: `src/gobby/mcp_proxy/tools/task_orchestration.py` (2,209 lines)
**Type**: "Kitchen Sink" Module
**Current State**: Contains a single massive `create_orchestration_registry` factory function that defines and registers multiple distinct MCP tools (`orchestrate_ready_tasks`, `poll_agent_status`, `spawn_review_agent`, `cleanup_reviewed_worktrees`).
**Strangler Fig Approach**:
> This is the ideal candidate for immediate decomposition.

1.  **Create Package**: `src/gobby/mcp_proxy/tools/orchestration/`
2.  **Extract Tools**: Move each tool function (e.g., `orchestrate_ready_tasks`, `poll_agent_status`) into its own isolated module.
3.  **Bridge**: Update `task_orchestration.py` to import these functions and register them.
4.  **Finalize**: Deprecate the massive factory in favor of a declarative registry.

## 2. Runner Up: `src/gobby/storage/tasks.py` (1,732 lines)
**Type**: "God Class"
**Current State**: `LocalTaskManager` handles database CRUD, hierarchical sorting, path caching string manipulation, and event listeners.
**Strangler Fig Approach**:
1.  **Extract Aspects**: Move complex logic into helper classes:
    - Hierarchical sorting (`order_tasks_hierarchically`) -> `TaskHierarchyManager`
    - Path caching (`compute_path_cache`) -> `TaskPathCache`
2.  **Delegate**: Modify `LocalTaskManager` to delegate to these new classes instead of implementing the logic inline.

## 3. Third Place: `src/gobby/workflows/engine.py` (1,338 lines)
**Type**: Complex Core Logic
**Current State**: `WorkflowEngine` handles event dispatch, state transitions, action execution, rule evaluation, and extensive audit logging.
**Strangler Fig Approach**:
1.  **Audit Logging**: The `_log_*` methods take up significant space. Extract to `AuditLogger`.
2.  **Evaluation**: Further separate the lifecycle evaluation and trigger logic.

## Other Large Files (>1000 lines)
- `src/gobby/storage/migrations.py` (1399 lines) - *Skip* (Nature of migrations)
- `src/gobby/servers/routes/mcp/tools.py` (1337 lines) - Likely routing logic, candidate for splitting by domain.
- `src/gobby/mcp_proxy/tools/tasks.py` (1335 lines) - Similar to orchestration, likely contains many task-related tools.
