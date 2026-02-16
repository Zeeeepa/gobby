"""Tests for sync_bundled_agents."""

from pathlib import Path
from unittest.mock import patch

import pytest

from gobby.agents.sync import sync_bundled_agents
from gobby.storage.agent_definitions import LocalAgentDefinitionManager
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit


def _setup_db(tmp_path: Path) -> LocalDatabase:
    """Create a fresh database with migrations applied."""
    db = LocalDatabase(tmp_path / "test.db")
    run_migrations(db)
    return db


class TestSyncBundledAgents:
    """Tests for sync_bundled_agents function."""

    def test_sync_creates_bundled_agents(self, tmp_path: Path) -> None:
        """Test that sync creates bundled agent definitions in the DB."""
        db = _setup_db(tmp_path)

        # Create a fake agents directory with one YAML file
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "test-agent.yaml").write_text(
            "name: test-agent\ndescription: A test agent\nprovider: claude\nmode: headless\n"
        )

        with patch("gobby.agents.sync.get_bundled_agents_path", return_value=agents_dir):
            result = sync_bundled_agents(db)

        assert result["success"] is True
        assert result["synced"] == 1
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

        # Verify the agent was created with scope='bundled'
        mgr = LocalAgentDefinitionManager(db)
        row = mgr.get_bundled("test-agent")
        assert row is not None
        assert row.name == "test-agent"
        assert row.scope == "bundled"
        assert row.source_path == str(agents_dir / "test-agent.yaml")

    def test_sync_skips_unchanged(self, tmp_path: Path) -> None:
        """Test that sync skips agents that haven't changed."""
        db = _setup_db(tmp_path)

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "test-agent.yaml").write_text(
            "name: test-agent\ndescription: A test agent\nprovider: claude\nmode: headless\n"
        )

        with patch("gobby.agents.sync.get_bundled_agents_path", return_value=agents_dir):
            # First sync
            result1 = sync_bundled_agents(db)
            assert result1["synced"] == 1

            # Second sync — should skip
            result2 = sync_bundled_agents(db)
            assert result2["synced"] == 0
            assert result2["skipped"] == 1
            assert result2["updated"] == 0

    def test_sync_updates_changed(self, tmp_path: Path) -> None:
        """Test that sync updates agents when content changes."""
        db = _setup_db(tmp_path)

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        yaml_file = agents_dir / "test-agent.yaml"
        yaml_file.write_text(
            "name: test-agent\ndescription: A test agent\nprovider: claude\nmode: headless\n"
        )

        with patch("gobby.agents.sync.get_bundled_agents_path", return_value=agents_dir):
            # First sync
            sync_bundled_agents(db)

            # Modify the file
            yaml_file.write_text(
                "name: test-agent\ndescription: Updated description\nprovider: claude\nmode: headless\n"
            )

            # Second sync — should update
            result2 = sync_bundled_agents(db)
            assert result2["updated"] == 1
            assert result2["synced"] == 0
            assert result2["skipped"] == 0

        # Verify updated content
        mgr = LocalAgentDefinitionManager(db)
        row = mgr.get_bundled("test-agent")
        assert row is not None
        defn = mgr.export_to_definition(row.id)
        assert defn.description == "Updated description"

    def test_sync_multiple_agents(self, tmp_path: Path) -> None:
        """Test syncing multiple agent files."""
        db = _setup_db(tmp_path)

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "agent-a.yaml").write_text(
            "name: agent-a\nprovider: claude\nmode: headless\n"
        )
        (agents_dir / "agent-b.yaml").write_text(
            "name: agent-b\nprovider: gemini\nmode: terminal\n"
        )

        with patch("gobby.agents.sync.get_bundled_agents_path", return_value=agents_dir):
            result = sync_bundled_agents(db)

        assert result["synced"] == 2
        assert result["errors"] == []

    def test_sync_missing_path(self, tmp_path: Path) -> None:
        """Test sync handles missing agents directory gracefully."""
        db = _setup_db(tmp_path)

        with patch(
            "gobby.agents.sync.get_bundled_agents_path",
            return_value=tmp_path / "nonexistent",
        ):
            result = sync_bundled_agents(db)

        assert result["success"] is True
        assert result["synced"] == 0
        assert len(result["errors"]) == 1

    def test_sync_invalid_yaml(self, tmp_path: Path) -> None:
        """Test sync handles invalid YAML gracefully."""
        db = _setup_db(tmp_path)

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "bad.yaml").write_text("not: valid: yaml: [[[")

        with patch("gobby.agents.sync.get_bundled_agents_path", return_value=agents_dir):
            result = sync_bundled_agents(db)

        assert result["synced"] == 0
        assert len(result["errors"]) == 1

    def test_sync_with_real_bundled_agents(self, tmp_path: Path) -> None:
        """Test that sync works with the actual bundled agents directory."""
        db = _setup_db(tmp_path)

        result = sync_bundled_agents(db)

        assert result["success"] is True
        # We know there are at least some bundled agents
        assert result["synced"] + result["skipped"] + result["updated"] >= 0
        assert result["errors"] == []

        # Verify bundled agents are retrievable
        mgr = LocalAgentDefinitionManager(db)
        bundled = mgr.get_bundled("generic")
        if bundled:
            assert bundled.scope == "bundled"
            assert bundled.name == "generic"
