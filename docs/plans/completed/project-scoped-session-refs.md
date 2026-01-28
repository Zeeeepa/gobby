# Plan: Project-Scoped Session Refs

## Overview

Make session refs (`#N`) project-scoped like tasks, and display them consistently instead of UUIDs.

**Current State:**
- Sessions have `project_id` (required) but `seq_num` is globally unique
- Task refs are project-scoped: `#5` in Project A ≠ `#5` in Project B
- Session refs are global: `#5` is unique across ALL projects
- Claude sees UUIDs for sessions, `#N` for tasks

## Constraints

- Backwards compatibility: global lookup fallback when `project_id` not provided
- Cross-project display must be unambiguous (e.g., `gobby#1` vs `other-project#1`)

---

## Phase 1: Schema & Storage Foundation

**Goal**: Update database schema and core storage layer to support project-scoped session refs.

**Tasks:**
- [ ] Add migration to change seq_num index from global to project-scoped (category: code)
- [ ] Update seq_num assignment in sessions.py to be per-project (category: code)
- [ ] Update resolve_session_reference() to accept project_id parameter (category: code)
- [ ] Update backfill migration for per-project numbering (category: code)

### Implementation Details

**Migration** (`src/gobby/storage/migrations.py`):
```sql
-- Drop global unique index
DROP INDEX IF EXISTS idx_sessions_seq_num;

-- Create project-scoped unique index
CREATE UNIQUE INDEX idx_sessions_seq_num ON sessions(project_id, seq_num);
```

**seq_num Assignment** (`src/gobby/storage/sessions.py` ~line 231-233):
```python
# Before
max_seq_row = self.db.fetchone("SELECT MAX(seq_num) as max_seq FROM sessions")

# After
max_seq_row = self.db.fetchone(
    "SELECT MAX(seq_num) as max_seq FROM sessions WHERE project_id = ?",
    (project_id,)
)
```

**Reference Resolution** (`src/gobby/storage/sessions.py` ~line 286-339):
```python
def resolve_session_reference(self, ref: str, project_id: str | None = None) -> str:
    """Resolve session reference.

    Supports:
    - #N: Project-scoped seq_num (requires project_id)
    - N: Integer string treated as #N
    - UUID: Full UUID
    - Prefix: UUID prefix (must be unambiguous)
    """
    seq_num_ref = ref.lstrip("#")
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

**Backfill Migration** (`src/gobby/storage/migrations.py` - `_migrate_backfill_session_seq_num_per_project`):

> **Note**: The snippet below was the pre-consolidation plan. The actual backfill now lives in
> `_migrate_backfill_session_seq_num_per_project()` in the migrations module, which handles
> per-project seq_num assignment during schema migration.

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

---

## Phase 2: CLI Integration

**Goal**: Update CLI commands to resolve session refs with project context.

**Tasks:**
- [ ] Add project_id parameter to resolve_session_id() in cli/utils.py (category: code)
- [ ] Update show_session and delete_session in cli/sessions.py (category: code)
- [ ] Update workflow commands in cli/workflows.py (category: code)
- [ ] Update claim_worktree in cli/worktrees.py (category: code)
- [ ] Update agent_stats in cli/agents.py (category: code)

### Implementation Details

**CLI Utils** (`src/gobby/cli/utils.py` ~line 121-152):
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

**Affected CLI Commands:**
- `cli/sessions.py`: `show_session`, `delete_session`
- `cli/workflows.py`: `workflow_status`, `clear_workflow`, `set_step`, `reset_workflow`, `disable_workflow`, `enable_workflow`
- `cli/worktrees.py`: `claim_worktree`
- `cli/agents.py`: `agent_stats`

---

## Phase 3: MCP Tools & Display

**Goal**: Update MCP tools to document `#N` format and display refs instead of UUIDs.

**Tasks:**
- [ ] Update hook context to display #N instead of UUID (category: code)
- [ ] Update MCP instructions to reference #N format (category: docs)
- [ ] Update task tool schemas to document #N format (category: docs)
- [ ] Update session tool schemas and resolution (category: code)
- [ ] Update workflow tool schemas and resolution (category: code)
- [ ] Update agent tool schemas and resolution (category: code)
- [ ] Update hub cross-project display to show project#N format (category: code)

### Implementation Details

**Hook Context Display** (`src/gobby/hooks/event_handlers.py` ~line 346-365):
```python
# Before
system_message = f"\nGobby Session ID: {session_id}"

# After
session_ref = f"#{session.seq_num}" if session.seq_num else session_id[:8]
system_message = f"\nGobby Session: {session_ref}"
```

**MCP Instructions** (`src/gobby/mcp_proxy/instructions.py` ~line 29-31):
Update to reference `#N` format instead of UUID.

**Tool Schema Updates:**
- `tools/tasks/_crud.py` - Document `#N` in session_id description
- `tools/tasks/_lifecycle.py` - Document `#N` in session_id description
- `tools/tasks/_session.py` - Document `#N` + pass project_id to resolution
- `tools/tasks/_context.py` - `get_workflow_state()` resolve with project_id
- `tools/workflows.py` - `get_workflow_status()` document `#N`, resolve with project_id
- `tools/session_messages.py` - `get_handoff_context()`, `get_session()`, `mark_loop_complete()`
- `tools/agents.py` - `can_spawn_agent()` document `#N`, resolve with project_id

**Hub Cross-Project Display** (`src/gobby/mcp_proxy/tools/hub.py` ~line 204-257):
```python
# Fetch project name alongside session data (requires JOIN with projects table)
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

---

## Phase 4: Tests

**Goal**: Update and add tests for project-scoped session refs.

**Tasks:**
- [ ] Update session resolution tests in test_cli_utils.py (category: test)
- [ ] Add project-scoped seq_num tests in test_sessions.py (category: test)

---

## Verification

1. Run migration on test database
2. Start new session, verify system prompt shows `Gobby Session: #1` (not UUID)
3. Verify `resolve_session_reference("#1", project_id)` works
4. Verify different projects can both have `#1` sessions
5. Test `list_cross_project_sessions()` shows `gobby#42` format
6. Run existing session tests

---

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| **Epic: Project-Scoped Session Refs** | #6204 | completed |
| **Phase 1: Schema & Storage Foundation** | #6205 | completed |
| Add migration to change seq_num index | #6212 | completed |
| Update seq_num assignment to be per-project | #6213 | completed |
| Update resolve_session_reference() to accept project_id | #6214 | completed |
| Update backfill migration for per-project numbering | #6215 | completed |
| **Phase 2: CLI Integration** | #6206 | completed |
| Add project_id parameter to resolve_session_id() | #6222 | completed |
| Update show_session and delete_session | #6223 | completed |
| Update workflow commands | #6224 | completed |
| Update claim_worktree | #6225 | completed |
| Update agent_stats | #6226 | completed |
| **Phase 3: MCP Tools & Display** | #6207 | completed |
| Update hook context to display #N | #6233 | completed |
| Update MCP instructions to reference #N format | #6234 | completed |
| Update task tool schemas | #6235 | completed |
| Update session tool schemas and resolution | #6237 | completed |
| Update workflow tool schemas and resolution | #6239 | completed |
| Update agent tool schemas and resolution | #6240 | completed |
| Update hub cross-project display | #6241 | completed |
| **Phase 4: Tests** | #6208 | completed |
| Update session resolution tests in test_cli_utils.py | #6242 | completed |
| Add project-scoped seq_num tests in test_sessions.py | #6243 | completed |
