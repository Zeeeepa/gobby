"""Tests for session-defaults.yaml loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.sync import load_session_defaults, sync_bundled_rules

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_session_defaults.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def manager(db: LocalDatabase) -> LocalWorkflowDefinitionManager:
    return LocalWorkflowDefinitionManager(db)


@pytest.fixture
def rules_dir(tmp_path) -> Path:
    d = tmp_path / "rules"
    d.mkdir()
    return d


class TestLoadSessionDefaults:
    """Test loading session variable defaults from YAML."""

    def test_loads_from_yaml_file(self, rules_dir) -> None:
        """Should load session_variables from YAML file."""
        (rules_dir / "session-defaults.yaml").write_text(
            """
session_variables:
  chat_mode: bypass
  mode_level: 2
  stop_attempts: 0
"""
        )
        defaults = load_session_defaults(rules_dir)

        assert defaults["chat_mode"] == "bypass"
        assert defaults["mode_level"] == 2
        assert defaults["stop_attempts"] == 0

    def test_loads_all_expected_defaults(self, rules_dir) -> None:
        """Should load all expected default variable values."""
        (rules_dir / "session-defaults.yaml").write_text(
            """
session_variables:
  chat_mode: bypass
  mode_level: 2
  unlocked_tools: []
  servers_listed: false
  listed_servers: []
  pre_existing_errors_triaged: false
  stop_attempts: 0
"""
        )
        defaults = load_session_defaults(rules_dir)

        assert defaults["chat_mode"] == "bypass"
        assert defaults["mode_level"] == 2
        assert defaults["unlocked_tools"] == []
        assert defaults["servers_listed"] is False
        assert defaults["listed_servers"] == []
        assert defaults["pre_existing_errors_triaged"] is False
        assert defaults["stop_attempts"] == 0

    def test_returns_empty_dict_when_missing(self, tmp_path) -> None:
        """Should return empty dict when file doesn't exist."""
        defaults = load_session_defaults(tmp_path / "nonexistent")
        assert defaults == {}

    def test_returns_empty_dict_when_no_session_variables(self, rules_dir) -> None:
        """Should return empty dict when file has no session_variables key."""
        (rules_dir / "session-defaults.yaml").write_text(
            """
rules:
  some-rule:
    event: before_tool
"""
        )
        defaults = load_session_defaults(rules_dir)
        assert defaults == {}


class TestSessionDefaultsSync:
    """Test that session-defaults.yaml is correctly handled by sync."""

    def test_session_defaults_skipped_by_rule_sync(self, db, rules_dir) -> None:
        """session-defaults.yaml without 'rules' key should be skipped, not error."""
        (rules_dir / "session-defaults.yaml").write_text(
            """
session_variables:
  chat_mode: bypass
  stop_attempts: 0
"""
        )
        result = sync_bundled_rules(db, rules_dir)

        # Should be skipped (no 'rules' key), not an error
        assert result["synced"] == 0
        assert result["skipped"] == 1
        assert result["errors"] == []


class TestBundledSessionDefaults:
    """Test the actual bundled session-defaults.yaml file."""

    def test_bundled_file_exists(self) -> None:
        """The bundled session-defaults.yaml should exist."""
        from gobby.workflows.sync import get_bundled_rules_path

        defaults_file = get_bundled_rules_path() / "session-defaults.yaml"
        assert defaults_file.exists(), f"Expected {defaults_file} to exist"

    def test_bundled_file_has_expected_variables(self) -> None:
        """The bundled file should have all expected default variables."""
        from gobby.workflows.sync import get_bundled_rules_path

        defaults = load_session_defaults(get_bundled_rules_path())

        expected_keys = {
            "chat_mode",
            "mode_level",
            "unlocked_tools",
            "servers_listed",
            "listed_servers",
            "pre_existing_errors_triaged",
            "stop_attempts",
        }
        assert expected_keys.issubset(defaults.keys()), (
            f"Missing keys: {expected_keys - defaults.keys()}"
        )

    def test_bundled_defaults_have_correct_values(self) -> None:
        """The bundled defaults should match the planned values."""
        from gobby.workflows.sync import get_bundled_rules_path

        defaults = load_session_defaults(get_bundled_rules_path())

        assert defaults["chat_mode"] == "bypass"
        assert defaults["mode_level"] == 2
        assert defaults["unlocked_tools"] == []
        assert defaults["servers_listed"] is False
        assert defaults["listed_servers"] == []
        assert defaults["pre_existing_errors_triaged"] is False
        assert defaults["stop_attempts"] == 0
