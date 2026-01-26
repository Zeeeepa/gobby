# Plan: Project-Scoped Session Refs

## Goal

Make session refs (`#N`) project-scoped like tasks, and display them consistently instead of UUIDs.

## Current State

- Sessions have `project_id` (required) but `seq_num` is globally unique
- Task refs are project-scoped: `#5` in Project A ≠ `#5` in Project B
- Session refs are global: `#5` is unique across ALL projects
- Claude sees UUIDs for sessions, `#N` for tasks

## Changes

### 1. Schema Migration (new migration)

**File:** `src/gobby/storage/migrations.py`

```sql
-- Drop global unique index
DROP INDEX IF EXISTS idx_sessions_seq_num;

-- Create project-scoped unique index
CREATE UNIQUE INDEX idx_sessions_seq_num ON sessions(project_id, seq_num);
```

### 2. Session seq_num Assignment

**File:** `src/gobby/storage/sessions.py` (~line 231-233)

Before:
```python
max_seq_row = self.db.fetchone("SELECT MAX(seq_num) as max_seq FROM sessions")
```

After:
```python
max_seq_row = self.db.fetchone(
    "SELECT MAX(seq_num) as max_seq FROM sessions WHERE project_id = ?",
    (project_id,)
)
```

### 3. Session Reference Resolution

**File:** `src/gobby/storage/sessions.py` (~line 286-339)

Update `resolve_session_reference()` to accept `project_id`:

```python
def resolve_session_reference(self, ref: str, project_id: str | None = None) -> str:
    """Resolve session reference.

    Supports:
    - #N: Project-scoped seq_num (requires project_id)
    - N: Integer string treated as #N
    - UUID: Full UUID
    - Prefix: UUID prefix (must be unambiguous)
    """
    # For #N format, require project_id
    if seq_num_ref.isdigit():
        seq_num = int(seq_num_ref)
        if project_id:
            row = self.db.fetchone(
                "SELECT id FROM sessions WHERE project_id = ? AND seq_num = ?",
                (project_id, seq_num)
            )
        else:
            # Fallback to global lookup for backwards compat
            row = self.db.fetchone(
                "SELECT id FROM sessions WHERE seq_num = ?",
                (seq_num,)
            )
```

### 4. Update Callers to Pass project_id

**File:** `src/gobby/cli/utils.py` (~line 121-152)

```python
def resolve_session_id(session_ref: str | None, project_id: str | None = None) -> str:
    """Resolve session reference to UUID."""
    # Get project_id from context if not provided
    if not project_id:
        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None

    manager = LocalSessionManager(db)
    return manager.resolve_session_reference(session_ref, project_id)
```

### 5. Hook Context Display

**File:** `src/gobby/hooks/event_handlers.py` (~line 346-365)

Before:
```python
system_message = f"\nGobby Session ID: {session_id}"
```

After:
```python
session_ref = f"#{session.seq_num}" if session.seq_num else session_id[:8]
system_message = f"\nGobby Session: {session_ref}"
```

### 6. MCP Instructions

**File:** `src/gobby/mcp_proxy/instructions.py` (~line 29-31)

Update to reference `#N` format instead of UUID.

### 7. Tool Schemas

**Files:**
- `src/gobby/mcp_proxy/tools/tasks/_crud.py`
- `src/gobby/mcp_proxy/tools/tasks/_lifecycle.py`
- `src/gobby/mcp_proxy/tools/tasks/_session.py`

Update session_id descriptions to document `#N, N, or UUID` format.

### 8. Update Hub Cross-Project Display

**File:** `src/gobby/mcp_proxy/tools/hub.py` (~line 204-257)

Update `list_cross_project_sessions()` to display project-qualified refs:

```python
# Fetch project name alongside session data
sessions = [
    {
        "ref": f"{project_name}#{session.seq_num}",  # e.g., "gobby#1"
        "session_id": row["id"],
        "project": project_name,
        "source": row["source"],
        ...
    }
]
```

This requires joining with projects table to get project name.

### 9. Backfill Migration

**File:** `src/gobby/storage/migrations_legacy.py`

Update `_backfill_session_seq_num()` to assign per-project:

```python
# Get all sessions grouped by project, ordered by created_at
sessions = db.fetchall("""
    SELECT id, project_id FROM sessions
    WHERE seq_num IS NULL
    ORDER BY project_id, created_at ASC, id ASC
""")

# Assign seq_num per project
current_project = None
seq_num = 0
for session in sessions:
    if session["project_id"] != current_project:
        current_project = session["project_id"]
        seq_num = 1
    else:
        seq_num += 1
    db.execute("UPDATE sessions SET seq_num = ? WHERE id = ?", (seq_num, session["id"]))
```

## Files to Modify

### Core Storage & Migration
| File | Change |
|------|--------|
| `src/gobby/storage/migrations.py` | Add migration to change index |
| `src/gobby/storage/sessions.py` | Project-scoped seq_num assignment + resolution |
| `src/gobby/storage/migrations_legacy.py` | Update backfill for per-project numbering |

### Hook & Instructions
| File | Change |
|------|--------|
| `src/gobby/hooks/event_handlers.py` | Display `#N` in system prompt |
| `src/gobby/mcp_proxy/instructions.py` | Update session ID guidance |

### MCP Tools - Task Related
| File | Change |
|------|--------|
| `src/gobby/mcp_proxy/tools/tasks/_crud.py` | Document `#N` in schema |
| `src/gobby/mcp_proxy/tools/tasks/_lifecycle.py` | Document `#N` in schema |
| `src/gobby/mcp_proxy/tools/tasks/_session.py` | Document `#N` in schema + pass project_id |
| `src/gobby/mcp_proxy/tools/tasks/_context.py` | `get_workflow_state()` - resolve with project_id |

### MCP Tools - Workflows
| File | Change |
|------|--------|
| `src/gobby/mcp_proxy/tools/workflows.py` | `get_workflow_status()` - document `#N`, resolve with project_id |

### MCP Tools - Sessions
| File | Change |
|------|--------|
| `src/gobby/mcp_proxy/tools/session_messages.py` | `get_handoff_context()`, `get_session()`, `mark_loop_complete()` - document `#N`, resolve with project_id |

### MCP Tools - Agents
| File | Change |
|------|--------|
| `src/gobby/mcp_proxy/tools/agents.py` | `can_spawn_agent()` - document `#N`, resolve with project_id |

### MCP Tools - Hub
| File | Change |
|------|--------|
| `src/gobby/mcp_proxy/tools/hub.py` | Update `list_cross_project_sessions()` to show `project#N` format |

### CLI Commands - Sessions
| File | Change |
|------|--------|
| `src/gobby/cli/sessions.py` | `show_session`, `delete_session` - resolve with project_id |
| `src/gobby/cli/utils.py` | `resolve_session_id()` - add project_id parameter |

### CLI Commands - Workflows
| File | Change |
|------|--------|
| `src/gobby/cli/workflows.py` | `workflow_status`, `clear_workflow`, `set_step`, `reset_workflow`, `disable_workflow`, `enable_workflow` - resolve with project_id |

### CLI Commands - Worktrees
| File | Change |
|------|--------|
| `src/gobby/cli/worktrees.py` | `claim_worktree` - resolve with project_id |

### CLI Commands - Agents
| File | Change |
|------|--------|
| `src/gobby/cli/agents.py` | `agent_stats` - resolve with project_id |

### Tests
| File | Change |
|------|--------|
| `tests/cli/test_cli_utils.py` | Update session resolution tests |
| `tests/storage/test_sessions.py` | Add project-scoped seq_num tests |

## Verification

1. Run migration on test database
2. Start new session, verify system prompt shows `Gobby Session: #1` (not UUID)
3. Verify `resolve_session_reference("#1", project_id)` works
4. Verify different projects can both have `#1` sessions
5. Test `list_cross_project_sessions()` shows `gobby#42` format
6. Run existing session tests
