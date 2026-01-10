# Gobby UI Specification Documents

These spec documents are designed for use with `expand_from_spec` to create task hierarchies.

## Usage

```python
# Expand a phase into tasks
call_tool("gobby-tasks", "expand_from_spec", {"spec_path": "docs/specs/ui/phase-0-tui.md"})

# Or create all phases as epics under a parent
parent = call_tool("gobby-tasks", "create_task", {"title": "Gobby UI Implementation", "task_type": "epic"})
for phase in range(8):
    call_tool("gobby-tasks", "expand_from_spec", {
        "spec_path": f"docs/specs/ui/phase-{phase}-*.md",
        "parent_task_id": parent["id"]
    })
```

## Phase Overview

| Phase | Spec | Description | Depends On |
|-------|------|-------------|------------|
| 0 | [phase-0-tui.md](phase-0-tui.md) | TUI Dashboard with Textual | - |
| 1 | [phase-1-web-foundation.md](phase-1-web-foundation.md) | Next.js + shadcn/ui foundation | Phase 0 |
| 2 | [phase-2-realtime.md](phase-2-realtime.md) | WebSocket real-time updates | Phase 1 |
| 3 | [phase-3-task-graph.md](phase-3-task-graph.md) | Cytoscape.js task visualization | Phase 2 |
| 4 | [phase-4-agent-orchestrator.md](phase-4-agent-orchestrator.md) | Agent spawning and monitoring | Phase 3 |
| 5 | [phase-5-mcp-observatory.md](phase-5-mcp-observatory.md) | MCP tool analytics | Phase 4 |
| 6 | [phase-6-mobile-pwa.md](phase-6-mobile-pwa.md) | Mobile PWA for remote access | Phase 5 |
| 7 | [phase-7-tauri.md](phase-7-tauri.md) | Native desktop wrapper | Phase 6 |

## Task Counts

| Phase | Sections | Checkboxes |
|-------|----------|------------|
| 0 - TUI | 9 | ~60 |
| 1 - Web Foundation | 8 | ~55 |
| 2 - Real-time | 5 | ~35 |
| 3 - Task Graph | 6 | ~40 |
| 4 - Agent Orchestrator | 6 | ~50 |
| 5 - MCP Observatory | 7 | ~50 |
| 6 - Mobile PWA | 7 | ~55 |
| 7 - Tauri | 9 | ~50 |
| **Total** | **57** | **~395** |

## Related Documents

- [UI Approach](../../design/ui-approach.md) - TUI-first strategy, mobile requirements
- [Design System](../../design/design-system.md) - Color tokens, typography, components
- [Tailwind Config](../../design/tailwind.config.ts) - Web styling configuration
- [UI Plan](../../plans/UI.md) - Full implementation plan with architecture

## Notes

- Each spec is self-contained with clear dependencies
- Checkboxes are structured for expand_from_spec parsing
- Sections map to epic-level tasks, checkboxes map to individual tasks
- TDD mode will create test tasks alongside implementation tasks
