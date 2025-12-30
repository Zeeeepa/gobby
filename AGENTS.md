## Task Tracking with Gobby

**IMPORTANT**: This project uses **Gobby's native task system** for ALL task tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why Gobby Tasks?

- Dependency-aware: Track blockers and relationships between tasks
- Git-friendly: Auto-syncs to `.gobby/tasks.jsonl` for version control
- Agent-optimized: MCP tools + JSON output + ready work detection
- Session-aware: Tasks link to sessions where discovered/worked
- Multi-CLI support: Works with Claude Code, Gemini CLI, and Codex

### Quick Start (MCP Tools)

**Check for ready work:**

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="list_ready_tasks",
    arguments={"limit": 10}
)
```

**Create new tasks:**

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="create_task",
    arguments={
        "title": "Fix authentication bug",
        "priority": 1,
        "task_type": "bug"
    }
)
```

**Claim and update:**

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="update_task",
    arguments={"task_id": "gt-abc123", "status": "in_progress"}
)
```

**Complete work:**

```python
mcp__gobby__call_tool(
    server_name="gobby-tasks",
    tool_name="close_task",
    arguments={"task_id": "gt-abc123", "reason": "completed"}
)
```

### CLI Commands

```bash
# List ready work (open tasks with no blocking dependencies)
gobby tasks list --ready

# Create task
gobby tasks create "Fix bug" -p 1 -t bug

# Update task
gobby tasks update gt-abc123 --status in_progress

# Close task
gobby tasks close gt-abc123 --reason "Fixed"

# Sync with git
gobby tasks sync
```

### Task Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `1` - High (major features, important bugs)
- `2` - Medium (default)
- `3` - Low (polish, optimization)

### Workflow for AI Agents

1. **Check ready work**: `list_ready_tasks` shows unblocked tasks
2. **Claim your task**: `update_task` with `status="in_progress"`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked task with `add_dependency`
5. **Complete**: `close_task` with reason
6. **Commit together**: Include `.gobby/tasks.jsonl` with code changes

### Auto-Sync

Gobby tasks automatically sync:

- Exports to `.gobby/tasks.jsonl` after changes (5s debounce)
- Imports from JSONL on daemon start
- Use `gobby tasks sync` to manually trigger

### Available MCP Tools

All accessed via `call_tool(server_name="gobby-tasks", ...)`:

**Task CRUD:**
| Tool | Description |
|------|-------------|
| `create_task` | Create a new task |
| `get_task` | Get task details with dependencies |
| `update_task` | Update task fields |
| `close_task` | Close a task with reason |
| `delete_task` | Delete a task |
| `list_tasks` | List tasks with filters |
| `add_label` | Add a label to a task |
| `remove_label` | Remove a label from a task |

**Dependencies:**
| Tool | Description |
|------|-------------|
| `add_dependency` | Add dependency between tasks |
| `remove_dependency` | Remove a dependency |
| `get_dependency_tree` | Get blockers/blocking tasks |
| `check_dependency_cycles` | Detect circular dependencies |
| `list_ready_tasks` | List unblocked tasks |
| `list_blocked_tasks` | List blocked tasks |

**Session & Sync:**
| Tool | Description |
|------|-------------|
| `link_task_to_session` | Associate task with session |
| `get_session_tasks` | Tasks linked to a session |
| `get_task_sessions` | Sessions that touched a task |
| `sync_tasks` | Trigger import/export |
| `get_sync_status` | Get sync status |

**LLM Expansion:**
| Tool | Description |
|------|-------------|
| `expand_task` | Break task into subtasks with AI |
| `analyze_complexity` | Get complexity score |
| `expand_all` | Expand all unexpanded tasks |
| `expand_from_spec` | Create tasks from PRD/spec |
| `suggest_next_task` | AI suggests next task to work on |

**Validation:**
| Tool | Description |
|------|-------------|
| `validate_task` | Validate task completion |
| `get_validation_status` | Get validation details |
| `reset_validation_count` | Reset failure count for retry |

### Managing AI-Generated Planning Documents

AI assistants often create planning and design documents during development:

- PLAN.md, IMPLEMENTATION.md, ARCHITECTURE.md
- DESIGN.md, CODEBASE_SUMMARY.md, INTEGRATION_PLAN.md
- TESTING_GUIDE.md, TECHNICAL_DESIGN.md, and similar files

**Best Practice: Use a dedicated directory for these ephemeral files**

**Recommended approach:**

- Create a `history/` directory in the project root
- Store ALL AI-generated planning/design docs in `history/`
- Keep the repository root clean and focused on permanent project files
- Only access `history/` when explicitly asked to review past planning

**Example .gitignore entry (optional):**

```
# AI planning documents (ephemeral)
history/
```

**Benefits:**

- Clean repository root
- Clear separation between ephemeral and permanent documentation
- Easy to exclude from version control if desired
- Preserves planning history for archeological research
- Reduces noise when browsing the project

### Important Rules

- Use gobby tasks for ALL task tracking
- Use MCP tools (`gobby-tasks`) for programmatic access
- Check `list_ready_tasks` before asking "what should I work on?"
- Store AI planning docs in `history/` directory
- Do NOT create markdown TODO lists
- Do NOT use external issue trackers
- Do NOT duplicate tracking systems
- Do NOT clutter repo root with planning documents
- ALWAYS use `uv run` for python commands (never `python` or `pytest` directly)

For more details, see [README.md](README.md) and [MCP_TOOLS.md](MCP_TOOLS.md).
