# Task Tools Module Dependencies

Verified via import testing on 2026-01-06.

## Module Dependency Graph

```
tasks.py (facade)
├── task_dependencies.py
│   └── InternalToolRegistry
│   └── get_project_context (utils)
├── task_readiness.py
│   └── InternalToolRegistry
│   └── get_project_context (utils)
├── task_sync.py
│   └── InternalToolRegistry
│   └── get_project_context (utils)
├── task_expansion.py (pre-existing)
│   └── InternalToolRegistry
│   └── TaskExpander
├── task_validation.py (pre-existing)
│   └── InternalToolRegistry
│   └── TaskValidator
└── internal.py (InternalToolRegistry)
```

## Import Order

All modules can be imported in any order without circular import issues:

1. `gobby.mcp_proxy.tools.internal` - Base registry (no dependencies)
2. `gobby.mcp_proxy.tools.task_dependencies` - Depends on internal
3. `gobby.mcp_proxy.tools.task_readiness` - Depends on internal
4. `gobby.mcp_proxy.tools.task_sync` - Depends on internal
5. `gobby.mcp_proxy.tools.task_expansion` - Depends on internal
6. `gobby.mcp_proxy.tools.task_validation` - Depends on internal
7. `gobby.mcp_proxy.tools.tasks` - Facade that imports all above

## Verification Results

```
✓ gobby.mcp_proxy.tools.tasks
✓ gobby.mcp_proxy.tools.task_dependencies
✓ gobby.mcp_proxy.tools.task_readiness
✓ gobby.mcp_proxy.tools.task_sync
✓ gobby.mcp_proxy.tools.task_expansion
✓ gobby.mcp_proxy.tools.task_validation
```

All imports successful with no circular import warnings.

## Line Counts (verified 2026-01-07)

| Module | Lines | Status |
|--------|-------|--------|
| task_dependencies.py | 183 | ✓ Under 400 |
| task_readiness.py | 253 | ✓ Under 400 |
| task_sync.py | 293 | ✓ Under 400 |
| task_expansion.py | 604 | ⚠ Pre-existing, future extraction candidate |
| task_validation.py | 483 | ⚠ Pre-existing, future extraction candidate |
| tasks.py | 1,992 | Facade (reduced from ~2,400) |
| __init__.py | 26 | ✓ Under 400 |

**Notes:**
- task_expansion.py and task_validation.py were extracted before this decomposition effort
- They exceed 400 lines and may benefit from further decomposition
- Newly extracted modules (dependencies, readiness, sync) are all under 400 lines
- All modules pass ruff linting
