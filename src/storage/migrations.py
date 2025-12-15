"""Database migrations for local storage."""

import logging
from typing import Callable

from gobby.storage.database import LocalDatabase

logger = logging.getLogger(__name__)

# Migration functions: (version, description, sql)
MIGRATIONS: list[tuple[int, str, str]] = [
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

    Args:
        db: LocalDatabase instance

    Returns:
        Number of migrations applied
    """
    current_version = get_current_version(db)
    applied = 0

    for version, description, sql in MIGRATIONS:
        if version > current_version:
            logger.debug(f"Applying migration {version}: {description}")
            try:
                # Execute migration SQL (may contain multiple statements)
                for statement in sql.strip().split(";"):
                    statement = statement.strip()
                    if statement:
                        db.execute(statement)

                # Record migration
                db.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                applied += 1
            except Exception as e:
                logger.error(f"Migration {version} failed: {e}")
                raise

    if applied > 0:
        logger.debug(f"Applied {applied} migration(s), now at version {version}")

    return applied
