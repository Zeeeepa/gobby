"""Tests for P2P message columns and agent_commands table migration.

Verifies migration v116:
- inter_session_messages gains message_type, metadata_json, delivered_at columns
- agent_commands table created with correct schema and indices
- InterSessionMessage dataclass handles new fields
"""

from __future__ import annotations

import json
import uuid

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.inter_session_messages import InterSessionMessage, InterSessionMessageManager
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_p2p_migration.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


_TEST_PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def _ensure_sessions(db: LocalDatabase, *session_ids: str) -> None:
    """Insert fake sessions for FK constraints."""
    # Ensure test project exists
    db.execute(
        """INSERT OR IGNORE INTO projects (id, name, repo_path, created_at, updated_at)
           VALUES (?, '_test', '/tmp/test', datetime('now'), datetime('now'))""",
        (_TEST_PROJECT_ID,),
    )
    for sid in session_ids:
        db.execute(
            """INSERT OR IGNORE INTO sessions
               (id, external_id, machine_id, source, project_id, status)
               VALUES (?, ?, 'test-machine', 'test', ?, 'active')""",
            (sid, sid, _TEST_PROJECT_ID),
        )


def _insert_message(db: LocalDatabase, msg_id: str | None = None, **extra: str) -> str:
    """Insert a test message with FK-safe sessions. Returns message ID."""
    msg_id = msg_id or str(uuid.uuid4())
    from_s = str(uuid.uuid4())
    to_s = str(uuid.uuid4())
    _ensure_sessions(db, from_s, to_s)

    cols = "id, from_session, to_session, content, priority, sent_at"
    vals = "?, ?, ?, ?, 'normal', datetime('now')"
    params: list[str] = [msg_id, from_s, to_s, "hello"]

    for col, val in extra.items():
        cols += f", {col}"
        vals += ", ?"
        params.append(val)

    db.execute(
        f"INSERT INTO inter_session_messages ({cols}) VALUES ({vals})",
        tuple(params),
    )
    return msg_id


# ═══════════════════════════════════════════════════════════════════════
# inter_session_messages new columns
# ═══════════════════════════════════════════════════════════════════════


class TestInterSessionMessageColumns:
    """New columns on inter_session_messages table."""

    def test_message_type_column_exists(self, db: LocalDatabase) -> None:
        """message_type column should exist with default 'message'."""
        msg_id = _insert_message(db)
        row = db.fetchone("SELECT message_type FROM inter_session_messages WHERE id = ?", (msg_id,))
        assert row is not None
        assert row["message_type"] == "message"

    def test_metadata_json_column_exists(self, db: LocalDatabase) -> None:
        """metadata_json column should exist and accept JSON."""
        metadata = json.dumps({"key": "value"})
        msg_id = _insert_message(db, metadata_json=metadata)
        row = db.fetchone("SELECT metadata_json FROM inter_session_messages WHERE id = ?", (msg_id,))
        assert row is not None
        assert json.loads(row["metadata_json"]) == {"key": "value"}

    def test_delivered_at_column_exists(self, db: LocalDatabase) -> None:
        """delivered_at column should exist and default to NULL."""
        msg_id = _insert_message(db)
        row = db.fetchone("SELECT delivered_at FROM inter_session_messages WHERE id = ?", (msg_id,))
        assert row is not None
        assert row["delivered_at"] is None

    def test_message_type_can_be_command(self, db: LocalDatabase) -> None:
        """message_type should accept 'command' value."""
        msg_id = _insert_message(db, message_type="command")
        row = db.fetchone("SELECT message_type FROM inter_session_messages WHERE id = ?", (msg_id,))
        assert row["message_type"] == "command"

    def test_undelivered_index_exists(self, db: LocalDatabase) -> None:
        """idx_ism_undelivered index should exist."""
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ism_undelivered'"
        )
        assert row is not None


# ═══════════════════════════════════════════════════════════════════════
# agent_commands table
# ═══════════════════════════════════════════════════════════════════════


class TestAgentCommandsTable:
    """agent_commands table creation and schema."""

    def test_table_exists(self, db: LocalDatabase) -> None:
        """agent_commands table should exist after migration."""
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_commands'"
        )
        assert row is not None

    def test_insert_command(self, db: LocalDatabase) -> None:
        """Should be able to insert an agent command."""
        cmd_id = str(uuid.uuid4())
        from_session = str(uuid.uuid4())
        to_session = str(uuid.uuid4())

        db.execute(
            """INSERT INTO agent_commands
               (id, from_session, to_session, command_text, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (cmd_id, from_session, to_session, "Run tests"),
        )

        row = db.fetchone("SELECT * FROM agent_commands WHERE id = ?", (cmd_id,))
        assert row is not None
        assert row["from_session"] == from_session
        assert row["to_session"] == to_session
        assert row["command_text"] == "Run tests"
        assert row["status"] == "pending"

    def test_allowed_tools_column(self, db: LocalDatabase) -> None:
        """allowed_tools should accept JSON array."""
        cmd_id = str(uuid.uuid4())
        tools = json.dumps(["Read", "Grep", "Glob"])
        db.execute(
            """INSERT INTO agent_commands
               (id, from_session, to_session, command_text, allowed_tools, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (cmd_id, str(uuid.uuid4()), str(uuid.uuid4()), "Search", tools),
        )
        row = db.fetchone("SELECT allowed_tools FROM agent_commands WHERE id = ?", (cmd_id,))
        assert json.loads(row["allowed_tools"]) == ["Read", "Grep", "Glob"]

    def test_allowed_mcp_tools_column(self, db: LocalDatabase) -> None:
        """allowed_mcp_tools should accept JSON array."""
        cmd_id = str(uuid.uuid4())
        mcp_tools = json.dumps(["gobby-tasks:create_task"])
        db.execute(
            """INSERT INTO agent_commands
               (id, from_session, to_session, command_text, allowed_mcp_tools, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (cmd_id, str(uuid.uuid4()), str(uuid.uuid4()), "Create task", mcp_tools),
        )
        row = db.fetchone("SELECT allowed_mcp_tools FROM agent_commands WHERE id = ?", (cmd_id,))
        assert json.loads(row["allowed_mcp_tools"]) == ["gobby-tasks:create_task"]

    def test_exit_condition_column(self, db: LocalDatabase) -> None:
        """exit_condition should accept text."""
        cmd_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO agent_commands
               (id, from_session, to_session, command_text, exit_condition, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (cmd_id, str(uuid.uuid4()), str(uuid.uuid4()), "Work", "task_tree_complete()"),
        )
        row = db.fetchone("SELECT exit_condition FROM agent_commands WHERE id = ?", (cmd_id,))
        assert row["exit_condition"] == "task_tree_complete()"

    def test_status_values(self, db: LocalDatabase) -> None:
        """Status should accept various lifecycle values."""
        for status in ("pending", "running", "completed", "failed", "cancelled"):
            cmd_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO agent_commands
                   (id, from_session, to_session, command_text, status)
                   VALUES (?, ?, ?, ?, ?)""",
                (cmd_id, str(uuid.uuid4()), str(uuid.uuid4()), "test", status),
            )
            row = db.fetchone("SELECT status FROM agent_commands WHERE id = ?", (cmd_id,))
            assert row["status"] == status

    def test_timestamps_default(self, db: LocalDatabase) -> None:
        """created_at should be auto-populated."""
        cmd_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO agent_commands
               (id, from_session, to_session, command_text, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (cmd_id, str(uuid.uuid4()), str(uuid.uuid4()), "test"),
        )
        row = db.fetchone("SELECT created_at FROM agent_commands WHERE id = ?", (cmd_id,))
        assert row["created_at"] is not None

    def test_to_session_index(self, db: LocalDatabase) -> None:
        """idx_agent_commands_to_session index should exist."""
        row = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_agent_commands_to_session'"
        )
        assert row is not None


# ═══════════════════════════════════════════════════════════════════════
# InterSessionMessage dataclass
# ═══════════════════════════════════════════════════════════════════════


class TestInterSessionMessageDataclass:
    """InterSessionMessage should include new fields."""

    def test_new_fields_in_dataclass(self) -> None:
        """Dataclass should have message_type, metadata_json, delivered_at."""
        msg = InterSessionMessage(
            id="test-id",
            from_session="s1",
            to_session="s2",
            content="hello",
            priority="normal",
            sent_at="2026-01-01T00:00:00",
            read_at=None,
            message_type="command",
            metadata_json='{"key": "value"}',
            delivered_at="2026-01-01T00:00:01",
        )
        assert msg.message_type == "command"
        assert msg.metadata_json == '{"key": "value"}'
        assert msg.delivered_at == "2026-01-01T00:00:01"

    def test_defaults(self) -> None:
        """New fields should have sensible defaults."""
        msg = InterSessionMessage(
            id="test-id",
            from_session="s1",
            to_session="s2",
            content="hello",
            priority="normal",
            sent_at="2026-01-01T00:00:00",
            read_at=None,
        )
        assert msg.message_type == "message"
        assert msg.metadata_json is None
        assert msg.delivered_at is None

    def test_to_dict_includes_new_fields(self) -> None:
        """to_dict should include the new fields."""
        msg = InterSessionMessage(
            id="test-id",
            from_session="s1",
            to_session="s2",
            content="hello",
            priority="normal",
            sent_at="2026-01-01T00:00:00",
            read_at=None,
            message_type="command",
            metadata_json='{"key": "val"}',
            delivered_at=None,
        )
        d = msg.to_dict()
        assert d["message_type"] == "command"
        assert d["metadata_json"] == '{"key": "val"}'
        assert d["delivered_at"] is None

    def test_from_row_includes_new_fields(self, db: LocalDatabase) -> None:
        """from_row should parse new columns from database."""
        metadata = json.dumps({"source": "test"})
        msg_id = _insert_message(db, message_type="command", metadata_json=metadata)
        row = db.fetchone("SELECT * FROM inter_session_messages WHERE id = ?", (msg_id,))
        msg = InterSessionMessage.from_row(row)
        assert msg.message_type == "command"
        assert msg.metadata_json == metadata
        assert msg.delivered_at is None

    def test_create_message_with_type(self, db: LocalDatabase) -> None:
        """create_message should support message_type parameter."""
        mgr = InterSessionMessageManager(db)
        _ensure_sessions(db, "sess-from", "sess-to")

        msg = mgr.create_message(
            from_session="sess-from",
            to_session="sess-to",
            content="run tests",
            message_type="command",
        )
        assert msg.message_type == "command"
