"""Tests for session-defaults rule-based initialization and variable sync."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody
from gobby.workflows.sync import sync_bundled_rules, sync_bundled_variables

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
        mode_rule = mgr.get_by_name("init-mode-level", include_templates=True)
        assert mode_rule is not None
        assert mode_rule.enabled

        stop_rule = mgr.get_by_name("init-stop-attempts", include_templates=True)
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
        assert len(yaml_files) >= 1, f"Expected >= 1 rule files, got {len(yaml_files)}"

    def test_bundled_defaults_sync_to_db(self, db) -> None:
        """The bundled session-defaults rules should sync to DB."""
        from gobby.workflows.sync import get_bundled_rules_path

        result = sync_bundled_rules(db, get_bundled_rules_path())
        assert result["errors"] == [], f"Sync errors: {result['errors']}"

    def test_synced_defaults_have_set_variable_effects(self, db) -> None:
        """initialize-session-defaults should use set_variable effects with per-effect when."""
        from gobby.workflows.sync import get_bundled_rules_path

        sync_bundled_rules(db, get_bundled_rules_path())
        mgr = LocalWorkflowDefinitionManager(db)
        rule = mgr.get_by_name("initialize-session-defaults", include_templates=True)
        assert rule is not None
        body = RuleDefinitionBody.model_validate_json(rule.definition_json)
        effects = body.resolved_effects
        assert len(effects) >= 14
        for effect in effects:
            assert effect.type == "set_variable"
            assert effect.when is not None  # each has per-effect when guard
            assert "is None" in effect.when

    def test_initializes_all_expected_variables(self, db) -> None:
        """initialize-session-defaults should set all expected session variables."""
        from gobby.workflows.sync import get_bundled_rules_path

        sync_bundled_rules(db, get_bundled_rules_path())
        mgr = LocalWorkflowDefinitionManager(db)
        rule = mgr.get_by_name("initialize-session-defaults", include_templates=True)
        assert rule is not None
        body = RuleDefinitionBody.model_validate_json(rule.definition_json)

        initialized_vars = {e.variable for e in body.resolved_effects}
        expected_vars = {
            "require_uv",
            "chat_mode",
            "mode_level",
            "stop_attempts",
            "max_stop_attempts",
            "task_claimed",
            "task_ref",
            "require_task_before_edit",
            "require_commit_before_close",
            "pre_existing_errors_triaged",
            "enforce_tool_schema_check",
            "servers_listed",
            "listed_servers",
            "unlocked_tools",
        }
        assert expected_vars.issubset(initialized_vars), (
            f"Missing: {expected_vars - initialized_vars}"
        )


class TestBundledVariablesSync:
    """Test that bundled variable definitions sync via multi-variable format."""

    def test_bundled_variables_dir_exists(self) -> None:
        """The bundled variables directory should exist with YAML files."""
        from gobby.workflows.sync import get_bundled_variables_path

        var_dir = get_bundled_variables_path()
        assert var_dir.is_dir(), f"Expected {var_dir} to be a directory"
        yaml_files = list(var_dir.glob("*.yaml"))
        assert len(yaml_files) >= 1, f"Expected >= 1 variable files, got {len(yaml_files)}"

    def test_bundled_variables_sync_to_db(self, db) -> None:
        """Bundled variable definitions should sync to DB without errors."""
        result = sync_bundled_variables(db)
        assert result["errors"] == [], f"Sync errors: {result['errors']}"
        assert result["synced"] == 14

    def test_synced_variables_have_correct_type(self, db) -> None:
        """All synced variables should have workflow_type='variable'."""
        sync_bundled_variables(db)
        mgr = LocalWorkflowDefinitionManager(db)
        rows = mgr.list_all(workflow_type="variable", include_deleted=False)
        assert len(rows) >= 14
        for row in rows:
            assert row.workflow_type == "variable"
            assert row.source == "template"

    def test_multi_variable_file_format(self, db, tmp_path) -> None:
        """A file with variables: dict should create multiple variable rows."""
        import gobby.workflows.sync as sync_mod

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "test-vars.yaml").write_text(
            """
tags: [test-tag]

variables:
  my_var_a:
    value: true
    description: Variable A
  my_var_b:
    value: 42
    description: Variable B
"""
        )

        original = sync_mod.get_bundled_variables_path
        sync_mod.get_bundled_variables_path = lambda: var_dir
        try:
            result = sync_bundled_variables(db)
        finally:
            sync_mod.get_bundled_variables_path = original

        assert result["synced"] == 2
        assert result["errors"] == []

        mgr = LocalWorkflowDefinitionManager(db)
        var_a = mgr.get_by_name("my_var_a", include_templates=True)
        assert var_a is not None
        assert var_a.workflow_type == "variable"
        body_a = json.loads(var_a.definition_json)
        assert body_a["value"] is True
        assert "test-tag" in (var_a.tags or [])

        var_b = mgr.get_by_name("my_var_b", include_templates=True)
        assert var_b is not None
        body_b = json.loads(var_b.definition_json)
        assert body_b["value"] == 42

    def test_variable_idempotent_resync(self, db) -> None:
        """Running sync twice should skip already-synced variables."""
        result1 = sync_bundled_variables(db)
        assert result1["synced"] == 14

        result2 = sync_bundled_variables(db)
        assert result2["synced"] == 0
        assert result2["skipped"] == 14

    def test_variable_orphan_cleanup(self, db, tmp_path) -> None:
        """Variables removed from disk should be soft-deleted."""
        import gobby.workflows.sync as sync_mod

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "vars.yaml").write_text(
            """
variables:
  temp_var:
    value: hello
"""
        )

        original = sync_mod.get_bundled_variables_path
        sync_mod.get_bundled_variables_path = lambda: var_dir
        try:
            sync_bundled_variables(db)

            # Remove from disk
            (var_dir / "vars.yaml").write_text(
                """
variables:
  other_var:
    value: world
"""
            )
            result = sync_bundled_variables(db)
        finally:
            sync_mod.get_bundled_variables_path = original

        assert result["orphaned"] == 1

    def test_all_expected_variables_synced(self, db) -> None:
        """All 14 expected session-default variables should be synced."""
        sync_bundled_variables(db)
        mgr = LocalWorkflowDefinitionManager(db)

        expected_vars = {
            "require_uv",
            "chat_mode",
            "mode_level",
            "stop_attempts",
            "max_stop_attempts",
            "task_claimed",
            "task_ref",
            "require_task_before_edit",
            "require_commit_before_close",
            "pre_existing_errors_triaged",
            "enforce_tool_schema_check",
            "servers_listed",
            "listed_servers",
            "unlocked_tools",
        }

        rows = mgr.list_all(workflow_type="variable", include_deleted=False)
        synced_names = {r.name for r in rows}
        assert expected_vars.issubset(synced_names), (
            f"Missing: {expected_vars - synced_names}"
        )
