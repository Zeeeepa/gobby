"""Tests for session-defaults.yaml rule-based initialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.sync import sync_bundled_rules

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


class TestSessionDefaultsSync:
    """Test that session-defaults.yaml syncs as proper rules."""

    def test_session_defaults_syncs_as_rules(self, db, rules_dir) -> None:
        """session-defaults.yaml with 'rules' key should create rule rows."""
        (rules_dir / "session-defaults.yaml").write_text(
            """
group: session-defaults
tags: [initialization]

rules:
  init-mode-level:
    description: "Default mode_level to 2"
    event: session_start
    priority: 1
    enabled: true
    effect:
      type: set_variable
      variable: mode_level
      value: 2

  init-stop-attempts:
    description: "Default stop_attempts to 0"
    event: session_start
    priority: 1
    enabled: true
    effect:
      type: set_variable
      variable: stop_attempts
      value: 0
"""
        )
        result = sync_bundled_rules(db, rules_dir)

        assert result["synced"] == 2
        assert result["errors"] == []

        # Verify rules exist in DB
        mgr = LocalWorkflowDefinitionManager(db)
        mode_rule = mgr.get_by_name("init-mode-level")
        assert mode_rule is not None
        assert mode_rule.enabled

        stop_rule = mgr.get_by_name("init-stop-attempts")
        assert stop_rule is not None
        assert stop_rule.enabled


class TestBundledSessionDefaults:
    """Test that bundled session-defaults rules sync correctly."""

    def test_bundled_defaults_dir_exists(self) -> None:
        """The bundled session-defaults directory should exist with YAML files."""
        from gobby.workflows.sync import get_bundled_rules_path

        defaults_dir = get_bundled_rules_path() / "session-defaults"
        assert defaults_dir.is_dir(), f"Expected {defaults_dir} to be a directory"
        yaml_files = list(defaults_dir.glob("*.yaml"))
        assert len(yaml_files) >= 10, f"Expected >= 10 rule files, got {len(yaml_files)}"

    def test_bundled_defaults_sync_to_db(self, db) -> None:
        """The bundled session-defaults rules should sync to DB."""
        from gobby.workflows.sync import get_bundled_rules_path

        result = sync_bundled_rules(db, get_bundled_rules_path())
        assert result["errors"] == [], f"Sync errors: {result['errors']}"
        # Should have synced at least the expected number of init rules
        assert result["synced"] >= 12, (
            f"Expected at least 12 init rules, got {result['synced']}"
        )

    def test_synced_defaults_have_set_variable_effect(self, db) -> None:
        """Session-default rules should use set_variable effect type."""
        import json

        from gobby.workflows.sync import get_bundled_rules_path

        sync_bundled_rules(db, get_bundled_rules_path())
        mgr = LocalWorkflowDefinitionManager(db)
        rule = mgr.get_by_name("init-mode-level")
        assert rule is not None
        body = json.loads(rule.definition_json)
        assert body["effect"]["type"] == "set_variable"
        assert body["effect"]["variable"] == "mode_level"
