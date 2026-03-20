import pytest
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations, get_current_version

pytestmark = pytest.mark.unit

def test_migration_161_backfill(tmp_path):
    """Test that migration 161 correctly backfills stats from existing messages."""
    db_path = tmp_path / "test_161.db"
    db = LocalDatabase(db_path)

    # 1. Create schema without the new columns (manually)
    # We only need schema_version, projects, sessions and session_messages for this test
    db.execute("""
    CREATE TABLE schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """)
    db.execute("INSERT INTO schema_version (version) VALUES (160)")

    db.execute("""
    CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );
    """)
    db.execute("INSERT INTO projects (id, name) VALUES ('proj-1', 'test-project')")

    db.execute("""
    CREATE TABLE sessions (
        id TEXT PRIMARY KEY,
        external_id TEXT NOT NULL,
        machine_id TEXT NOT NULL,
        source TEXT NOT NULL,
        project_id TEXT NOT NULL REFERENCES projects(id),
        title TEXT,
        status TEXT DEFAULT 'active'
    );
    """)

    db.execute("""
    CREATE TABLE session_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        message_index INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_name TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    # 2. Insert test data
    session_id = "sess-1"
    db.execute("INSERT INTO sessions (id, external_id, machine_id, source, project_id) VALUES (?, 'ext-1', 'mach-1', 'gemini', 'proj-1')", (session_id,))

    # message 0: user
    db.execute("INSERT INTO session_messages (session_id, message_index, role, content, timestamp) VALUES (?, 0, 'user', 'hello', '2026-03-20T10:00:00')", (session_id,))
    # message 1: assistant (turn 1 - thinking)
    db.execute("INSERT INTO session_messages (session_id, message_index, role, content, timestamp) VALUES (?, 1, 'assistant', 'thinking...', '2026-03-20T10:00:01')", (session_id,))
    # message 2: assistant (turn 1 - tool call)
    db.execute("INSERT INTO session_messages (session_id, message_index, role, content, tool_name, timestamp) VALUES (?, 2, 'assistant', '', 'Grep', '2026-03-20T10:00:02')", (session_id,))
    # message 3: tool result
    db.execute("INSERT INTO session_messages (session_id, message_index, role, content, timestamp) VALUES (?, 3, 'tool', 'matches found', '2026-03-20T10:00:03')", (session_id,))
    # message 4: assistant (turn 1 - final response)
    db.execute("INSERT INTO session_messages (session_id, message_index, role, content, timestamp) VALUES (?, 4, 'assistant', 'I found it.', '2026-03-20T10:00:04')", (session_id,))

    # Add another session with no messages
    db.execute("INSERT INTO sessions (id, external_id, machine_id, source, project_id) VALUES ('sess-empty', 'ext-2', 'mach-1', 'gemini', 'proj-1')")

    # 3. Run migrations
    run_migrations(db)

    # 4. Verify version
    assert get_current_version(db) == 161

    # 5. Verify sess-1 stats
    row = db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
    assert row["message_count"] == 5
    assert row["turn_count"] == 3
    assert row["tool_call_count"] == 1
    assert row["last_assistant_content"] == "I found it."

    # 6. Verify sess-empty stats
    row_empty = db.fetchone("SELECT * FROM sessions WHERE id = 'sess-empty'")
    assert row_empty["message_count"] == 0
    assert row_empty["turn_count"] == 0
    assert row_empty["tool_call_count"] == 0
    assert row_empty["last_assistant_content"] is None

def test_migration_161_fresh_install(tmp_path):
    """Test that a fresh install has the columns and starts at correct version."""
    db_path = tmp_path / "fresh.db"
    db = LocalDatabase(db_path)

    run_migrations(db)
    assert get_current_version(db) == 161

    # PRAGMA table_info(sessions)
    columns = {row["name"] for row in db.fetchall("PRAGMA table_info(sessions)")}
    assert "message_count" in columns
    assert "turn_count" in columns
    assert "tool_call_count" in columns
    assert "last_assistant_content" in columns
