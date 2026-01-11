"""Database migrations for local storage."""

import logging
import uuid
from collections.abc import Callable

from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)

# Migration can be SQL string or a callable that takes LocalDatabase
MigrationAction = str | Callable[[LocalDatabase], None]


def _backfill_seq_num(db: LocalDatabase) -> None:
    """
    Backfill seq_num values for existing tasks.

    Assigns sequential numbers per project, ordered by created_at.
    Tasks within the same project get contiguous seq_num values starting from 1.
    """
    # Get all projects that have tasks
    projects = db.fetchall("SELECT DISTINCT project_id FROM tasks WHERE seq_num IS NULL")

    if not projects:
        logger.debug("No tasks need seq_num backfill")
        return

    for project in projects:
        project_id = project["project_id"]

        # Get tasks for this project, ordered by creation time
        tasks = db.fetchall(
            """
            SELECT id FROM tasks
            WHERE project_id = ? AND seq_num IS NULL
            ORDER BY created_at ASC, id ASC
            """,
            (project_id,),
        )

        # Find the max existing seq_num for this project (in case of partial migration)
        max_seq_row = db.fetchone(
            "SELECT MAX(seq_num) as max_seq FROM tasks WHERE project_id = ?",
            (project_id,),
        )
        next_seq = ((max_seq_row["max_seq"] if max_seq_row else None) or 0) + 1

        # Assign sequential numbers
        for task in tasks:
            db.execute(
                "UPDATE tasks SET seq_num = ? WHERE id = ?",
                (next_seq, task["id"]),
            )
            next_seq += 1

        logger.debug(f"Backfilled seq_num for {len(tasks)} tasks in project {project_id}")


def _migrate_task_ids_to_uuid(db: LocalDatabase) -> None:
    """
    Convert gt-* format task IDs to full UUIDs.

    This migration:
    1. Finds all tasks with gt-* format IDs
    2. Generates a full UUID for each (preserving short hash in last segment)
    3. Updates the task ID and all foreign key references

    Note: This is a data migration that modifies existing data.
    Foreign keys must be disabled during the update to avoid constraint violations.
    """
    # Get all tasks with gt-* format IDs
    tasks = db.fetchall("SELECT id FROM tasks WHERE id LIKE 'gt-%'")

    if not tasks:
        logger.debug("No gt-* format task IDs found, skipping migration")
        return

    logger.debug(f"Converting {len(tasks)} task IDs from gt-* to UUID format")

    # Build ID mapping: old_id -> new_uuid
    id_mapping: dict[str, str] = {}
    for task in tasks:
        old_id = task["id"]
        # Generate UUID, embedding old short hash in final segment for traceability
        # Format: xxxxxxxx-xxxx-4xxx-yxxx-{old_hash}xxxxxx
        short_hash = old_id.replace("gt-", "")  # 6 hex chars
        new_uuid = str(uuid.uuid4())
        # Embed old hash at start of last segment for debugging/traceability
        parts = new_uuid.split("-")
        # Last segment is 12 chars, replace first 6 with old hash
        parts[4] = short_hash + parts[4][6:]
        new_id = "-".join(parts)
        id_mapping[old_id] = new_id

    # Disable foreign keys for bulk update
    db.execute("PRAGMA foreign_keys = OFF")

    try:
        # Update tasks table (primary key)
        for old_id, new_id in id_mapping.items():
            db.execute("UPDATE tasks SET id = ? WHERE id = ?", (new_id, old_id))

        # Update parent_task_id references in tasks table
        for old_id, new_id in id_mapping.items():
            db.execute(
                "UPDATE tasks SET parent_task_id = ? WHERE parent_task_id = ?",
                (new_id, old_id),
            )

        # Update task_dependencies table (both task_id and depends_on columns)
        for old_id, new_id in id_mapping.items():
            db.execute(
                "UPDATE task_dependencies SET task_id = ? WHERE task_id = ?",
                (new_id, old_id),
            )
            db.execute(
                "UPDATE task_dependencies SET depends_on = ? WHERE depends_on = ?",
                (new_id, old_id),
            )

        # Update session_tasks table
        for old_id, new_id in id_mapping.items():
            db.execute(
                "UPDATE session_tasks SET task_id = ? WHERE task_id = ?",
                (new_id, old_id),
            )

        # Update task_validation_history table
        for old_id, new_id in id_mapping.items():
            db.execute(
                "UPDATE task_validation_history SET task_id = ? WHERE task_id = ?",
                (new_id, old_id),
            )

        # Update task_selection_history table
        for old_id, new_id in id_mapping.items():
            db.execute(
                "UPDATE task_selection_history SET task_id = ? WHERE task_id = ?",
                (new_id, old_id),
            )

        # Update worktrees table (task_id column)
        for old_id, new_id in id_mapping.items():
            db.execute(
                "UPDATE worktrees SET task_id = ? WHERE task_id = ?",
                (new_id, old_id),
            )

        logger.debug(f"Successfully converted {len(id_mapping)} task IDs to UUID format")

    finally:
        # Re-enable foreign keys
        db.execute("PRAGMA foreign_keys = ON")


def _backfill_path_cache(db: LocalDatabase) -> None:
    """
    Backfill path_cache values for existing tasks.

    Computes hierarchical paths by traversing parent chains.
    Processes root tasks first, then children to ensure parent paths exist.
    """
    from gobby.storage.tasks import LocalTaskManager

    task_mgr = LocalTaskManager(db)

    # Get all tasks that have seq_num but no path_cache, ordered by hierarchy depth
    # Use a recursive CTE to determine depth and process root tasks first
    tasks = db.fetchall(
        """
        WITH RECURSIVE task_depth AS (
            -- Base case: root tasks (no parent)
            SELECT id, 0 as depth
            FROM tasks
            WHERE parent_task_id IS NULL
            AND seq_num IS NOT NULL
            AND path_cache IS NULL

            UNION ALL

            -- Recursive case: children (only if parent has seq_num)
            SELECT t.id, td.depth + 1
            FROM tasks t
            JOIN task_depth td ON t.parent_task_id = td.id
            WHERE t.seq_num IS NOT NULL
            AND t.path_cache IS NULL
        )
        SELECT id FROM task_depth ORDER BY depth ASC
        """
    )

    if not tasks:
        logger.debug("No tasks need path_cache backfill")
        return

    # Compute and store path for each task
    updated = 0
    for task in tasks:
        path = task_mgr.update_path_cache(task["id"])
        if path:
            updated += 1

    logger.debug(f"Backfilled path_cache for {updated} tasks")


# Migration functions: (version, description, sql_or_callable)
MIGRATIONS: list[tuple[int, str, MigrationAction]] = [
    (
        1,
        "Create schema_version table",
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        2,
        "Create projects table",
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            repo_path TEXT,
            github_url TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
        """,
    ),
    (
        3,
        "Create sessions table",
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            cli_key TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            source TEXT NOT NULL,
            project_id TEXT REFERENCES projects(id),
            title TEXT,
            status TEXT DEFAULT 'active',
            jsonl_path TEXT,
            summary_path TEXT,
            summary_markdown TEXT,
            cwd TEXT,
            git_branch TEXT,
            parent_session_id TEXT REFERENCES sessions(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_cli_key ON sessions(cli_key);
        CREATE INDEX IF NOT EXISTS idx_sessions_machine_id ON sessions(machine_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_unique
            ON sessions(cli_key, machine_id, source);
        """,
    ),
    (
        4,
        "Create mcp_servers table",
        """
        CREATE TABLE IF NOT EXISTS mcp_servers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            transport TEXT NOT NULL,
            url TEXT,
            command TEXT,
            args TEXT,
            env TEXT,
            headers TEXT,
            enabled INTEGER DEFAULT 1,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_mcp_servers_name ON mcp_servers(name);
        CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled);
        """,
    ),
    (
        5,
        "Create tools table",
        """
        CREATE TABLE IF NOT EXISTS tools (
            id TEXT PRIMARY KEY,
            mcp_server_id TEXT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            input_schema TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(mcp_server_id, name)
        );
        CREATE INDEX IF NOT EXISTS idx_tools_server_id ON tools(mcp_server_id);
        CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(name);
        """,
    ),
    (
        6,
        "Remove cwd column from sessions (use project_id instead)",
        """
        PRAGMA foreign_keys = OFF;
        INSERT OR IGNORE INTO projects (id, name, repo_path, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000000', '_orphaned', NULL, datetime('now'), datetime('now'));
        CREATE TABLE sessions_new (
            id TEXT PRIMARY KEY,
            cli_key TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            source TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id),
            title TEXT,
            status TEXT DEFAULT 'active',
            jsonl_path TEXT,
            summary_path TEXT,
            summary_markdown TEXT,
            git_branch TEXT,
            parent_session_id TEXT REFERENCES sessions(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO sessions_new (id, cli_key, machine_id, source, project_id, title, status, jsonl_path, summary_path, summary_markdown, git_branch, parent_session_id, created_at, updated_at)
        SELECT id, cli_key, machine_id, source, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'), title, status, jsonl_path, summary_path, summary_markdown, git_branch, parent_session_id, created_at, updated_at FROM sessions;
        DROP TABLE sessions;
        ALTER TABLE sessions_new RENAME TO sessions;
        CREATE INDEX IF NOT EXISTS idx_sessions_cli_key ON sessions(cli_key);
        CREATE INDEX IF NOT EXISTS idx_sessions_machine_id ON sessions(machine_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_unique ON sessions(cli_key, machine_id, source);
        PRAGMA foreign_keys = ON;
        """,
    ),
    (
        7,
        "Add project_id to mcp_servers (required, no global servers)",
        """
        PRAGMA foreign_keys = OFF;
        CREATE TABLE mcp_servers_new (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            transport TEXT NOT NULL,
            url TEXT,
            command TEXT,
            args TEXT,
            env TEXT,
            headers TEXT,
            enabled INTEGER DEFAULT 1,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO projects (id, name, repo_path, created_at, updated_at)
        VALUES ('00000000-0000-0000-0000-000000000001', '_migrated', NULL, datetime('now'), datetime('now'));
        INSERT INTO mcp_servers_new (id, name, project_id, transport, url, command, args, env, headers, enabled, description, created_at, updated_at)
        SELECT id, name, '00000000-0000-0000-0000-000000000001', transport, url, command, args, env, headers, enabled, description, created_at, updated_at FROM mcp_servers;
        DROP TABLE mcp_servers;
        ALTER TABLE mcp_servers_new RENAME TO mcp_servers;
        CREATE INDEX IF NOT EXISTS idx_mcp_servers_name ON mcp_servers(name);
        CREATE INDEX IF NOT EXISTS idx_mcp_servers_project_id ON mcp_servers(project_id);
        CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_servers_name_project
            ON mcp_servers(name, project_id);
        PRAGMA foreign_keys = ON;
        """,
    ),
    (
        8,
        "Rename cli_key to external_id in sessions table",
        """
        PRAGMA foreign_keys = OFF;
        CREATE TABLE sessions_new (
            id TEXT PRIMARY KEY,
            external_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            source TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id),
            title TEXT,
            status TEXT DEFAULT 'active',
            jsonl_path TEXT,
            summary_path TEXT,
            summary_markdown TEXT,
            git_branch TEXT,
            parent_session_id TEXT REFERENCES sessions(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO sessions_new (id, external_id, machine_id, source, project_id, title, status, jsonl_path, summary_path, summary_markdown, git_branch, parent_session_id, created_at, updated_at)
        SELECT id, cli_key, machine_id, source, project_id, title, status, jsonl_path, summary_path, summary_markdown, git_branch, parent_session_id, created_at, updated_at FROM sessions;
        DROP TABLE sessions;
        ALTER TABLE sessions_new RENAME TO sessions;
        CREATE INDEX IF NOT EXISTS idx_sessions_external_id ON sessions(external_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_machine_id ON sessions(machine_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_unique ON sessions(external_id, machine_id, source);
        PRAGMA foreign_keys = ON;
        """,
    ),
    (
        9,
        "Create task system tables (tasks, dependencies, session linkages)",
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id),
            parent_task_id TEXT REFERENCES tasks(id),
            discovered_in_session_id TEXT REFERENCES sessions(id),
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 2,
            type TEXT DEFAULT 'task',
            assignee TEXT,
            labels TEXT,
            closed_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);

        CREATE TABLE IF NOT EXISTS task_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            depends_on TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            dep_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, depends_on, dep_type)
        );
        CREATE INDEX IF NOT EXISTS idx_deps_task ON task_dependencies(task_id);
        CREATE INDEX IF NOT EXISTS idx_deps_depends_on ON task_dependencies(depends_on);

        CREATE TABLE IF NOT EXISTS session_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(session_id, task_id, action)
        );
        CREATE INDEX IF NOT EXISTS idx_session_tasks_session ON session_tasks(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_tasks_task ON session_tasks(task_id);
        """,
    ),
    (
        10,
        "Add platform_id column to tasks for future fleet sync",
        """
        ALTER TABLE tasks ADD COLUMN platform_id TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_platform_id
            ON tasks(platform_id) WHERE platform_id IS NOT NULL;
        """,
    ),
    (
        11,
        "Add compaction columns to tasks",
        """
        ALTER TABLE tasks ADD COLUMN compacted_at TEXT;
        ALTER TABLE tasks ADD COLUMN summary TEXT;
        """,
    ),
    (
        12,
        "Create workflow state and handoff tables",
        """
        CREATE TABLE IF NOT EXISTS workflow_states (
            session_id TEXT PRIMARY KEY,
            workflow_name TEXT NOT NULL,
            phase TEXT NOT NULL,
            phase_entered_at TEXT,
            phase_action_count INTEGER DEFAULT 0,
            total_action_count INTEGER DEFAULT 0,
            artifacts TEXT,
            observations TEXT,
            reflection_pending INTEGER DEFAULT 0,
            context_injected INTEGER DEFAULT 0,
            variables TEXT,
            task_list TEXT,
            current_task_index INTEGER DEFAULT 0,
            files_modified_this_task INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS workflow_handoffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            workflow_name TEXT NOT NULL,
            from_session_id TEXT REFERENCES sessions(id),
            phase TEXT,
            artifacts TEXT,
            pending_tasks TEXT,
            notes TEXT,
            consumed_at TEXT,
            consumed_by_session TEXT REFERENCES sessions(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_handoffs_project ON workflow_handoffs(project_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_handoffs_consumed ON workflow_handoffs(consumed_at);
        """,
    ),
    (
        13,
        "Drop workflow_handoffs table (replaced by sessions.summary_markdown)",
        """
        DROP TABLE IF EXISTS workflow_handoffs;
        """,
    ),
    (
        14,
        "Add task validation columns",
        """
        ALTER TABLE tasks ADD COLUMN validation_status TEXT CHECK(validation_status IN ('pending', 'valid', 'invalid'));
        ALTER TABLE tasks ADD COLUMN validation_feedback TEXT;
        ALTER TABLE tasks ADD COLUMN original_instruction TEXT;
        """,
    ),
    (
        15,
        "Create session messages tables",
        """
        CREATE TABLE IF NOT EXISTS session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            content_type TEXT DEFAULT 'text',
            tool_name TEXT,
            tool_input TEXT,
            tool_result TEXT,
            timestamp TEXT NOT NULL,
            raw_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(session_id, message_index)
        );

        CREATE INDEX IF NOT EXISTS idx_session_messages_session ON session_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_messages_role ON session_messages(role);
        CREATE INDEX IF NOT EXISTS idx_session_messages_timestamp ON session_messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_session_messages_tool ON session_messages(tool_name);

        CREATE TABLE IF NOT EXISTS session_message_state (
            session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
            last_byte_offset INTEGER DEFAULT 0,
            last_message_index INTEGER DEFAULT 0,
            last_processed_at TEXT,
            processing_errors INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        16,
        "Add transcript_processed column to sessions",
        """
        ALTER TABLE sessions ADD COLUMN transcript_processed BOOLEAN DEFAULT FALSE;

        CREATE INDEX IF NOT EXISTS idx_sessions_pending_transcript
            ON sessions(status, transcript_processed)
            WHERE status = 'expired' AND transcript_processed = FALSE;
        """,
    ),
    (
        17,
        "Create memory system tables (memories, skills, session_memories)",
        """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id),
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            source_type TEXT,
            source_session_id TEXT REFERENCES sessions(id),
            importance REAL DEFAULT 0.5,
            access_count INTEGER DEFAULT 0,
            last_accessed_at TEXT,
            embedding BLOB,
            tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
        CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
        CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);

        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id),
            name TEXT NOT NULL,
            description TEXT,
            trigger_pattern TEXT,
            instructions TEXT NOT NULL,
            source_session_id TEXT REFERENCES sessions(id),
            tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skills_project ON skills(project_id);
        CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);

        CREATE TABLE IF NOT EXISTS session_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(session_id, memory_id, action)
        );
        CREATE INDEX IF NOT EXISTS idx_session_memories_session ON session_memories(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_memories_memory ON session_memories(memory_id);
        """,
    ),
    (
        18,
        "Add expansion fields to tasks table",
        """
        ALTER TABLE tasks ADD COLUMN details TEXT;
        ALTER TABLE tasks ADD COLUMN test_strategy TEXT;
        ALTER TABLE tasks ADD COLUMN complexity_score INTEGER;
        ALTER TABLE tasks ADD COLUMN estimated_subtasks INTEGER;
        ALTER TABLE tasks ADD COLUMN expansion_context TEXT;
        """,
    ),
    (
        19,
        "Add enhanced validation fields",
        """
        ALTER TABLE tasks ADD COLUMN validation_criteria TEXT;
        ALTER TABLE tasks ADD COLUMN use_external_validator INTEGER DEFAULT 0;
        ALTER TABLE tasks ADD COLUMN validation_fail_count INTEGER DEFAULT 0;
        """,
    ),
    (
        20,
        "Add compact_markdown column to sessions for compaction handoff",
        """
        ALTER TABLE sessions ADD COLUMN compact_markdown TEXT;
        """,
    ),
    (
        21,
        "Create tool_embeddings table for semantic search",
        """
        CREATE TABLE IF NOT EXISTS tool_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
            server_name TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            embedding BLOB NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_dim INTEGER NOT NULL,
            text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(tool_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tool_embeddings_tool ON tool_embeddings(tool_id);
        CREATE INDEX IF NOT EXISTS idx_tool_embeddings_server ON tool_embeddings(server_name);
        CREATE INDEX IF NOT EXISTS idx_tool_embeddings_project ON tool_embeddings(project_id);
        CREATE INDEX IF NOT EXISTS idx_tool_embeddings_hash ON tool_embeddings(text_hash);
        """,
    ),
    (
        22,
        "Add workflow integration columns to tasks table",
        """
        ALTER TABLE tasks ADD COLUMN workflow_name TEXT;
        ALTER TABLE tasks ADD COLUMN verification TEXT;
        ALTER TABLE tasks ADD COLUMN sequence_order INTEGER;
        CREATE INDEX IF NOT EXISTS idx_tasks_workflow ON tasks(workflow_name);
        CREATE INDEX IF NOT EXISTS idx_tasks_sequence ON tasks(workflow_name, sequence_order);
        """,
    ),
    (
        23,
        "Rename discovered_in_session_id to created_in_session_id and add close tracking columns",
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE tasks_new (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id),
            parent_task_id TEXT REFERENCES tasks(id),
            created_in_session_id TEXT REFERENCES sessions(id),
            closed_in_session_id TEXT REFERENCES sessions(id),
            closed_commit_sha TEXT,
            closed_at TEXT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 2,
            type TEXT DEFAULT 'task',
            assignee TEXT,
            labels TEXT,
            closed_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            platform_id TEXT,
            compacted_at TEXT,
            summary TEXT,
            validation_status TEXT CHECK(validation_status IN ('pending', 'valid', 'invalid')),
            validation_feedback TEXT,
            original_instruction TEXT,
            details TEXT,
            test_strategy TEXT,
            complexity_score INTEGER,
            estimated_subtasks INTEGER,
            expansion_context TEXT,
            validation_criteria TEXT,
            use_external_validator INTEGER DEFAULT 0,
            validation_fail_count INTEGER DEFAULT 0,
            workflow_name TEXT,
            verification TEXT,
            sequence_order INTEGER
        );

        INSERT INTO tasks_new (
            id, project_id, parent_task_id, created_in_session_id,
            closed_in_session_id, closed_commit_sha, closed_at,
            title, description, status, priority, type, assignee, labels,
            closed_reason, created_at, updated_at, platform_id,
            compacted_at, summary, validation_status, validation_feedback,
            original_instruction, details, test_strategy, complexity_score,
            estimated_subtasks, expansion_context, validation_criteria,
            use_external_validator, validation_fail_count,
            workflow_name, verification, sequence_order
        )
        SELECT
            id, project_id, parent_task_id, discovered_in_session_id,
            NULL, NULL, NULL,
            title, description, status, priority, type, assignee, labels,
            closed_reason, created_at, updated_at, platform_id,
            compacted_at, summary, validation_status, validation_feedback,
            original_instruction, details, test_strategy, complexity_score,
            estimated_subtasks, expansion_context, validation_criteria,
            use_external_validator, validation_fail_count,
            workflow_name, verification, sequence_order
        FROM tasks;

        DROP TABLE tasks;
        ALTER TABLE tasks_new RENAME TO tasks;

        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_platform_id
            ON tasks(platform_id) WHERE platform_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_tasks_workflow ON tasks(workflow_name);
        CREATE INDEX IF NOT EXISTS idx_tasks_sequence ON tasks(workflow_name, sequence_order);
        CREATE INDEX IF NOT EXISTS idx_tasks_created_session ON tasks(created_in_session_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_closed_session ON tasks(closed_in_session_id);

        PRAGMA foreign_keys = ON;
        """,
    ),
    # Migration 24: Create workflow_audit_log table for explainability/audit trail
    (
        24,
        "Create workflow_audit_log table for workflow explainability",
        """
        CREATE TABLE IF NOT EXISTS workflow_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            phase TEXT NOT NULL,
            event_type TEXT NOT NULL,       -- 'tool_call', 'rule_eval', 'transition', 'exit_check', 'approval'
            tool_name TEXT,                 -- For tool_call events
            rule_id TEXT,                   -- Which rule was evaluated
            condition TEXT,                 -- The 'when' clause evaluated
            result TEXT NOT NULL,           -- 'allow', 'block', 'transition', 'skip', 'approved', 'rejected', 'pending'
            reason TEXT,                    -- Human-readable explanation
            context TEXT,                   -- JSON: Additional context (tool args, state snapshot)
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_audit_session ON workflow_audit_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON workflow_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type ON workflow_audit_log(event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_result ON workflow_audit_log(result);
        """,
    ),
    (
        25,
        "Add validation_override_reason column to tasks",
        """
        ALTER TABLE tasks ADD COLUMN validation_override_reason TEXT;
        """,
    ),
    (
        26,
        "Rename phase columns to step in workflow tables",
        """
        PRAGMA foreign_keys = OFF;

        -- Rename columns in workflow_states table
        CREATE TABLE workflow_states_new (
            session_id TEXT PRIMARY KEY,
            workflow_name TEXT NOT NULL,
            step TEXT NOT NULL,
            step_entered_at TEXT,
            step_action_count INTEGER DEFAULT 0,
            total_action_count INTEGER DEFAULT 0,
            artifacts TEXT,
            observations TEXT,
            reflection_pending INTEGER DEFAULT 0,
            context_injected INTEGER DEFAULT 0,
            variables TEXT,
            task_list TEXT,
            current_task_index INTEGER DEFAULT 0,
            files_modified_this_task INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        INSERT INTO workflow_states_new (
            session_id, workflow_name, step, step_entered_at, step_action_count,
            total_action_count, artifacts, observations, reflection_pending,
            context_injected, variables, task_list, current_task_index,
            files_modified_this_task, created_at, updated_at
        )
        SELECT
            session_id, workflow_name, phase, phase_entered_at, phase_action_count,
            total_action_count, artifacts, observations, reflection_pending,
            context_injected, variables, task_list, current_task_index,
            files_modified_this_task, created_at, updated_at
        FROM workflow_states;

        DROP TABLE workflow_states;
        ALTER TABLE workflow_states_new RENAME TO workflow_states;

        -- Rename column in workflow_audit_log table
        CREATE TABLE workflow_audit_log_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            step TEXT NOT NULL,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            rule_id TEXT,
            condition TEXT,
            result TEXT NOT NULL,
            reason TEXT,
            context TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        INSERT INTO workflow_audit_log_new (
            id, session_id, timestamp, step, event_type, tool_name,
            rule_id, condition, result, reason, context
        )
        SELECT
            id, session_id, timestamp, phase, event_type, tool_name,
            rule_id, condition, result, reason, context
        FROM workflow_audit_log;

        DROP TABLE workflow_audit_log;
        ALTER TABLE workflow_audit_log_new RENAME TO workflow_audit_log;

        CREATE INDEX IF NOT EXISTS idx_audit_session ON workflow_audit_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON workflow_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type ON workflow_audit_log(event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_result ON workflow_audit_log(result);

        PRAGMA foreign_keys = ON;
        """,
    ),
    (
        27,
        "Remove platform_id column from tasks table",
        """
        DROP INDEX IF EXISTS idx_tasks_platform_id;
        ALTER TABLE tasks DROP COLUMN platform_id;
        """,
    ),
    (
        28,
        "Create tool_metrics table for tracking tool call statistics",
        """
        CREATE TABLE IF NOT EXISTS tool_metrics (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            server_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            total_latency_ms REAL NOT NULL DEFAULT 0,
            avg_latency_ms REAL,
            last_called_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, server_name, tool_name)
        );
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_project ON tool_metrics(project_id);
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_server ON tool_metrics(server_name);
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_tool ON tool_metrics(tool_name);
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_call_count ON tool_metrics(call_count DESC);
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_last_called ON tool_metrics(last_called_at);
        """,
    ),
    (
        29,
        "Create tool_schema_hashes table for incremental tool re-indexing",
        """
        CREATE TABLE IF NOT EXISTS tool_schema_hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            project_id TEXT NOT NULL,
            schema_hash TEXT NOT NULL,
            last_verified_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, server_name, tool_name)
        );
        CREATE INDEX IF NOT EXISTS idx_schema_hashes_server ON tool_schema_hashes(server_name);
        CREATE INDEX IF NOT EXISTS idx_schema_hashes_project ON tool_schema_hashes(project_id);
        CREATE INDEX IF NOT EXISTS idx_schema_hashes_verified ON tool_schema_hashes(last_verified_at);
        """,
    ),
    (
        30,
        "Add commits column to tasks table for commit linking",
        """
        ALTER TABLE tasks ADD COLUMN commits TEXT;
        """,
    ),
    (
        31,
        "Create task_validation_history table and add escalation columns to tasks",
        """
        CREATE TABLE IF NOT EXISTS task_validation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            iteration INTEGER NOT NULL,
            status TEXT NOT NULL,
            feedback TEXT,
            issues TEXT,
            context_type TEXT,
            context_summary TEXT,
            validator_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_validation_history_task ON task_validation_history(task_id);

        ALTER TABLE tasks ADD COLUMN escalated_at TEXT;
        ALTER TABLE tasks ADD COLUMN escalation_reason TEXT;
        """,
    ),
    (
        32,
        "Create tool_metrics_daily table for aggregated historical metrics",
        """
        CREATE TABLE IF NOT EXISTS tool_metrics_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            server_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            date TEXT NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            total_latency_ms REAL NOT NULL DEFAULT 0,
            avg_latency_ms REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, server_name, tool_name, date)
        );
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_daily_project ON tool_metrics_daily(project_id);
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_daily_date ON tool_metrics_daily(date);
        CREATE INDEX IF NOT EXISTS idx_tool_metrics_daily_server ON tool_metrics_daily(server_name);
        """,
    ),
    (
        33,
        "Add agent_depth and spawned_by_agent_id columns to sessions table",
        """
        ALTER TABLE sessions ADD COLUMN agent_depth INTEGER DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN spawned_by_agent_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_sessions_agent_depth ON sessions(agent_depth);
        CREATE INDEX IF NOT EXISTS idx_sessions_spawned_by ON sessions(spawned_by_agent_id);
        """,
    ),
    (
        34,
        "Create agent_runs table for tracking spawned agent executions",
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            parent_session_id TEXT NOT NULL REFERENCES sessions(id),
            child_session_id TEXT REFERENCES sessions(id),
            workflow_name TEXT,
            provider TEXT NOT NULL,
            model TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            prompt TEXT NOT NULL,
            result TEXT,
            error TEXT,
            tool_calls_count INTEGER DEFAULT 0,
            turns_used INTEGER DEFAULT 0,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_agent_runs_parent_session ON agent_runs(parent_session_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_child_session ON agent_runs(child_session_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_provider ON agent_runs(provider);
        """,
    ),
    (
        35,
        "Add terminal pickup metadata fields to sessions table",
        """
        ALTER TABLE sessions ADD COLUMN workflow_name TEXT;
        ALTER TABLE sessions ADD COLUMN agent_run_id TEXT REFERENCES agent_runs(id) ON DELETE SET NULL;
        ALTER TABLE sessions ADD COLUMN context_injected INTEGER DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN original_prompt TEXT;
        CREATE INDEX IF NOT EXISTS idx_sessions_workflow ON sessions(workflow_name);
        CREATE INDEX IF NOT EXISTS idx_sessions_agent_run ON sessions(agent_run_id);
        """,
    ),
    (
        36,
        "Create worktrees table for git worktree management",
        """
        CREATE TABLE IF NOT EXISTS worktrees (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            branch_name TEXT NOT NULL,
            worktree_path TEXT NOT NULL,
            base_branch TEXT DEFAULT 'main',
            agent_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            merged_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_worktrees_project ON worktrees(project_id);
        CREATE INDEX IF NOT EXISTS idx_worktrees_status ON worktrees(status);
        CREATE INDEX IF NOT EXISTS idx_worktrees_task ON worktrees(task_id);
        CREATE INDEX IF NOT EXISTS idx_worktrees_session ON worktrees(agent_session_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_worktrees_branch ON worktrees(project_id, branch_name);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_worktrees_path ON worktrees(worktree_path);
        """,
    ),
    (
        37,
        "Create session_stop_signals table for autonomous stop infrastructure",
        """
        CREATE TABLE IF NOT EXISTS session_stop_signals (
            session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            reason TEXT,
            requested_at TEXT NOT NULL,
            acknowledged_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_stop_signals_pending
            ON session_stop_signals(acknowledged_at)
            WHERE acknowledged_at IS NULL;
        """,
    ),
    (
        38,
        "Create loop_progress table for autonomous progress tracking",
        """
        CREATE TABLE IF NOT EXISTS loop_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            progress_type TEXT NOT NULL,
            tool_name TEXT,
            details TEXT,
            recorded_at TEXT NOT NULL,
            is_high_value INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_loop_progress_session
            ON loop_progress(session_id, recorded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_loop_progress_high_value
            ON loop_progress(session_id, is_high_value, recorded_at DESC)
            WHERE is_high_value = 1;
        """,
    ),
    (
        39,
        "Create task_selection_history table for stuck detection",
        """
        CREATE TABLE IF NOT EXISTS task_selection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            context TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_task_selection_session
            ON task_selection_history(session_id, selected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_task_selection_task
            ON task_selection_history(session_id, task_id, selected_at DESC);
        """,
    ),
    (
        40,
        "Rename type column to task_type in tasks table",
        """
        ALTER TABLE tasks RENAME COLUMN type TO task_type;
        """,
    ),
    (
        41,
        "Create session_artifacts table with FTS5 for full-text search",
        """
        CREATE TABLE IF NOT EXISTS session_artifacts (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT,
            source_file TEXT,
            line_start INTEGER,
            line_end INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_session_artifacts_session ON session_artifacts(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_artifacts_type ON session_artifacts(artifact_type);
        CREATE INDEX IF NOT EXISTS idx_session_artifacts_created ON session_artifacts(created_at);
        CREATE VIRTUAL TABLE IF NOT EXISTS session_artifacts_fts USING fts5(content);
        """,
    ),
    (
        42,
        "Add id column to session_artifacts_fts for JOIN support",
        """
        DROP TABLE IF EXISTS session_artifacts_fts;
        CREATE VIRTUAL TABLE IF NOT EXISTS session_artifacts_fts USING fts5(id UNINDEXED, content);
        """,
    ),
    (
        43,
        "Create merge_resolutions and merge_conflicts tables",
        """
        CREATE TABLE IF NOT EXISTS merge_resolutions (
            id TEXT PRIMARY KEY,
            worktree_id TEXT NOT NULL REFERENCES worktrees(id) ON DELETE CASCADE,
            source_branch TEXT NOT NULL,
            target_branch TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            tier_used TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_merge_resolutions_worktree ON merge_resolutions(worktree_id);
        CREATE INDEX IF NOT EXISTS idx_merge_resolutions_status ON merge_resolutions(status);
        CREATE INDEX IF NOT EXISTS idx_merge_resolutions_source_branch ON merge_resolutions(source_branch);
        CREATE INDEX IF NOT EXISTS idx_merge_resolutions_target_branch ON merge_resolutions(target_branch);
        CREATE TABLE IF NOT EXISTS merge_conflicts (
            id TEXT PRIMARY KEY,
            resolution_id TEXT NOT NULL REFERENCES merge_resolutions(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            ours_content TEXT,
            theirs_content TEXT,
            resolved_content TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_merge_conflicts_resolution ON merge_conflicts(resolution_id);
        CREATE INDEX IF NOT EXISTS idx_merge_conflicts_file_path ON merge_conflicts(file_path);
        CREATE INDEX IF NOT EXISTS idx_merge_conflicts_status ON merge_conflicts(status);
        """,
    ),
    (
        44,
        "Add token usage columns to sessions table",
        """
        ALTER TABLE sessions ADD COLUMN usage_input_tokens INTEGER DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN usage_output_tokens INTEGER DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN usage_cache_creation_tokens INTEGER DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN usage_cache_read_tokens INTEGER DEFAULT 0;
        ALTER TABLE sessions ADD COLUMN usage_total_cost_usd REAL DEFAULT 0.0;
        """,
    ),
    (
        45,
        "Add terminal_context column to sessions table",
        """
        ALTER TABLE sessions ADD COLUMN terminal_context TEXT;
        """,
    ),
    (
        46,
        "Drop skills table",
        """
        DROP TABLE IF EXISTS skills;
        """,
    ),
    (
        47,
        "Create memory_crossrefs table for linking related memories",
        """
        CREATE TABLE IF NOT EXISTS memory_crossrefs (
            source_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            similarity REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_id, target_id)
        );
        CREATE INDEX IF NOT EXISTS idx_crossrefs_source ON memory_crossrefs(source_id);
        CREATE INDEX IF NOT EXISTS idx_crossrefs_target ON memory_crossrefs(target_id);
        CREATE INDEX IF NOT EXISTS idx_crossrefs_similarity ON memory_crossrefs(similarity DESC);
        """,
    ),
    (
        48,
        "Add GitHub integration columns to tasks table",
        """
        ALTER TABLE tasks ADD COLUMN github_issue_number INTEGER;
        ALTER TABLE tasks ADD COLUMN github_pr_number INTEGER;
        ALTER TABLE tasks ADD COLUMN github_repo TEXT;
        """,
    ),
    (
        49,
        "Add github_repo column to projects table",
        """
        ALTER TABLE projects ADD COLUMN github_repo TEXT;
        """,
    ),
    (
        50,
        "Add Linear integration columns to tasks table",
        """
        ALTER TABLE tasks ADD COLUMN linear_issue_id TEXT;
        ALTER TABLE tasks ADD COLUMN linear_team_id TEXT;
        """,
    ),
    (
        51,
        "Add linear_team_id column to projects table",
        """
        ALTER TABLE projects ADD COLUMN linear_team_id TEXT;
        """,
    ),
    (
        52,
        "Add seq_num and path_cache columns to tasks table for human-friendly IDs",
        """
        ALTER TABLE tasks ADD COLUMN seq_num INTEGER;
        ALTER TABLE tasks ADD COLUMN path_cache TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_seq_num ON tasks(project_id, seq_num);
        CREATE INDEX IF NOT EXISTS idx_tasks_path_cache ON tasks(path_cache);
        """,
    ),
    (
        53,
        "Convert gt-* task IDs to full UUIDs",
        _migrate_task_ids_to_uuid,
    ),
    (
        54,
        "Backfill seq_num for existing tasks",
        _backfill_seq_num,
    ),
    (
        55,
        "Backfill path_cache for existing tasks",
        _backfill_path_cache,
    ),
    (
        56,
        "Add merge_state column to worktrees table",
        """
        ALTER TABLE worktrees ADD COLUMN merge_state TEXT;
        """,
    ),
]


def get_current_version(db: LocalDatabase) -> int:
    """Get current schema version from database."""
    try:
        row = db.fetchone("SELECT MAX(version) as version FROM schema_version")
        return row["version"] if row and row["version"] else 0
    except Exception:
        return 0


def run_migrations(db: LocalDatabase) -> int:
    """
    Run pending migrations.

    Supports both SQL string migrations and Python callable migrations.

    Args:
        db: LocalDatabase instance

    Returns:
        Number of migrations applied
    """
    current_version = get_current_version(db)
    applied = 0
    last_version = current_version

    for version, description, action in MIGRATIONS:
        if version > current_version:
            logger.debug(f"Applying migration {version}: {description}")
            try:
                if callable(action):
                    # Python data migration
                    action(db)
                else:
                    # SQL migration (may contain multiple statements)
                    for statement in action.strip().split(";"):
                        statement = statement.strip()
                        if statement:
                            db.execute(statement)

                # Record migration
                db.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                applied += 1
                last_version = version
            except Exception as e:
                logger.error(f"Migration {version} failed: {e}")
                raise

    if applied > 0:
        logger.debug(f"Applied {applied} migration(s), now at version {last_version}")

    return applied
