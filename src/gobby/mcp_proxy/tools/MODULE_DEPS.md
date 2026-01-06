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
