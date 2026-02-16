"""Tests for migration 107: agent_definitions scope CHECK constraint via table-recreate."""

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    """Fresh database with all migrations applied."""
    database = LocalDatabase(tmp_path / "gobby-hub.db")
    run_migrations(database)
    yield database
    database.close()


def _get_create_sql(db: LocalDatabase) -> str:
    """Return the CREATE TABLE statement for agent_definitions."""
    row = db.fetchone(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='agent_definitions'"
    )
    return row["sql"] if row else ""


class TestMigration107FreshDatabase:
    """Tests on a fresh (baseline) database."""

    def test_scope_column_has_check_constraint(self, db: LocalDatabase) -> None:
        """Baseline schema should include CHECK on scope."""
        sql = _get_create_sql(db)
        assert "CHECK" in sql
        assert "'bundled'" in sql
        assert "'global'" in sql
        assert "'project'" in sql

    def test_scope_column_exists(self, db: LocalDatabase) -> None:
        """scope column should exist."""
        columns = {row["name"] for row in db.fetchall("PRAGMA table_info(agent_definitions)")}
        assert "scope" in columns

    def test_source_path_column_exists(self, db: LocalDatabase) -> None:
        """source_path column should exist."""
        columns = {row["name"] for row in db.fetchall("PRAGMA table_info(agent_definitions)")}
        assert "source_path" in columns

    def test_version_column_exists(self, db: LocalDatabase) -> None:
        """version column should exist."""
        columns = {row["name"] for row in db.fetchall("PRAGMA table_info(agent_definitions)")}
        assert "version" in columns

    def test_composite_unique_index_exists(self, db: LocalDatabase) -> None:
        """idx_agent_defs_name_scope_project should exist."""
        indexes = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_agent_defs_name_scope_project'"
        )
        assert len(indexes) == 1

    def test_old_indexes_absent(self, db: LocalDatabase) -> None:
        """Old per-project/global unique indexes should not exist."""
        for idx_name in ("idx_agent_defs_project_name", "idx_agent_defs_global_name"):
            indexes = db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (idx_name,),
            )
            assert len(indexes) == 0, f"Expected {idx_name} to be absent"

    def test_invalid_scope_rejected(self, db: LocalDatabase) -> None:
        """Inserting an invalid scope value should fail."""
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO agent_definitions (id, name, scope, created_at, updated_at) "
                "VALUES ('bad-1', 'test', 'invalid_scope', datetime('now'), datetime('now'))"
            )


class TestMigration107Upgrade:
    """Tests simulating an upgrade from pre-107 database."""

    @pytest.fixture
    def upgrade_db(self, tmp_path):
        """Create a database at version 106 with agent_definitions lacking CHECK."""
        database = LocalDatabase(tmp_path / "upgrade.db")

        # Bootstrap schema_version
        database.execute(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        database.execute("INSERT INTO schema_version (version) VALUES (106)")

        # Create projects table (required for FK)
        database.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        database.execute("INSERT INTO projects (id, name) VALUES ('proj-1', 'test-project')")

        # Create agent_definitions as it would exist at v106 (after migrations 92+94,
        # but without scope/source_path/version columns — no CHECK constraint)
        database.execute("""
            CREATE TABLE IF NOT EXISTS agent_definitions (
                id TEXT PRIMARY KEY,
                project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                role TEXT,
                goal TEXT,
                personality TEXT,
                instructions TEXT,
                provider TEXT NOT NULL DEFAULT 'claude',
                model TEXT,
                mode TEXT NOT NULL DEFAULT 'headless',
                terminal TEXT DEFAULT 'auto',
                isolation TEXT,
                base_branch TEXT DEFAULT 'main',
                timeout REAL DEFAULT 120.0,
                max_turns INTEGER DEFAULT 10,
                default_workflow TEXT,
                sandbox_config TEXT,
                skill_profile TEXT,
                workflows TEXT,
                lifecycle_variables TEXT,
                default_variables TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Old-style indexes
        database.execute(
            "CREATE UNIQUE INDEX idx_agent_defs_project_name "
            "ON agent_definitions(project_id, name) WHERE project_id IS NOT NULL"
        )
        database.execute(
            "CREATE UNIQUE INDEX idx_agent_defs_global_name "
            "ON agent_definitions(name) WHERE project_id IS NULL"
        )
        database.execute("CREATE INDEX idx_agent_defs_project ON agent_definitions(project_id)")
        database.execute("CREATE INDEX idx_agent_defs_provider ON agent_definitions(provider)")

        # Seed some rows to verify data survives the recreate
        database.execute(
            "INSERT INTO agent_definitions (id, name, provider, created_at, updated_at) "
            "VALUES ('global-1', 'agent-global', 'claude', datetime('now'), datetime('now'))"
        )
        database.execute(
            "INSERT INTO agent_definitions (id, name, provider, project_id, created_at, updated_at) "
            "VALUES ('proj-1-def', 'agent-proj', 'gemini', 'proj-1', datetime('now'), datetime('now'))"
        )

        yield database
        database.close()

    def test_upgrade_adds_check_constraint(self, upgrade_db: LocalDatabase) -> None:
        """Table-recreate should add CHECK constraint."""
        run_migrations(upgrade_db)
        sql = _get_create_sql(upgrade_db)
        assert "CHECK" in sql
        assert "'bundled'" in sql

    def test_upgrade_preserves_global_row(self, upgrade_db: LocalDatabase) -> None:
        """Global agent rows should survive and get scope='global'."""
        run_migrations(upgrade_db)
        row = upgrade_db.fetchone("SELECT * FROM agent_definitions WHERE id = 'global-1'")
        assert row is not None
        assert row["name"] == "agent-global"
        assert row["scope"] == "global"
        assert row["provider"] == "claude"

    def test_upgrade_backfills_project_scope(self, upgrade_db: LocalDatabase) -> None:
        """Rows with project_id should get scope='project'."""
        run_migrations(upgrade_db)
        row = upgrade_db.fetchone("SELECT * FROM agent_definitions WHERE id = 'proj-1-def'")
        assert row is not None
        assert row["scope"] == "project"
        assert row["project_id"] == "proj-1"

    def test_upgrade_sets_version_default(self, upgrade_db: LocalDatabase) -> None:
        """version column should default to '1.0' for migrated rows."""
        run_migrations(upgrade_db)
        row = upgrade_db.fetchone("SELECT version FROM agent_definitions WHERE id = 'global-1'")
        assert row is not None
        assert row["version"] == "1.0"

    def test_upgrade_source_path_null(self, upgrade_db: LocalDatabase) -> None:
        """source_path should be NULL for migrated rows."""
        run_migrations(upgrade_db)
        row = upgrade_db.fetchone("SELECT source_path FROM agent_definitions WHERE id = 'global-1'")
        assert row is not None
        assert row["source_path"] is None

    def test_upgrade_invalid_scope_rejected(self, upgrade_db: LocalDatabase) -> None:
        """After upgrade, invalid scope values should be rejected."""
        run_migrations(upgrade_db)
        with pytest.raises(Exception):
            upgrade_db.execute(
                "INSERT INTO agent_definitions (id, name, scope, created_at, updated_at) "
                "VALUES ('bad-1', 'test', 'bogus', datetime('now'), datetime('now'))"
            )

    def test_upgrade_composite_index_created(self, upgrade_db: LocalDatabase) -> None:
        """New composite unique index should exist after upgrade."""
        run_migrations(upgrade_db)
        indexes = upgrade_db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_agent_defs_name_scope_project'"
        )
        assert len(indexes) == 1

    def test_upgrade_old_indexes_dropped(self, upgrade_db: LocalDatabase) -> None:
        """Old per-project/global unique indexes should be gone."""
        run_migrations(upgrade_db)
        for idx_name in ("idx_agent_defs_project_name", "idx_agent_defs_global_name"):
            indexes = upgrade_db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (idx_name,),
            )
            assert len(indexes) == 0, f"Expected {idx_name} to be absent"

    def test_upgrade_row_count_preserved(self, upgrade_db: LocalDatabase) -> None:
        """All rows should survive the table-recreate."""
        run_migrations(upgrade_db)
        count = upgrade_db.fetchone("SELECT COUNT(*) AS cnt FROM agent_definitions")
        assert count["cnt"] == 2
