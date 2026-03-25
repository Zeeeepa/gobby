"""Tests for workflow definition synchronization (sync.py).

Tests sync edge cases, error handling, orphan cleanup, and variable sync.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path: Path) -> LocalDatabase:
    """Create a temporary database for sync tests."""
    db_path = tmp_path / "test_sync.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def manager(db: LocalDatabase) -> LocalWorkflowDefinitionManager:
    return LocalWorkflowDefinitionManager(db)


# ═══════════════════════════════════════════════════════════════════════
# resolve_sync_placeholders
# ═══════════════════════════════════════════════════════════════════════


class TestResolveSyncPlaceholders:
    """Tests for resolve_sync_placeholders."""

    def test_no_placeholder_returns_unchanged(self) -> None:
        from gobby.workflows.sync import resolve_sync_placeholders

        result = resolve_sync_placeholders('{"event": "before_tool"}')
        assert result == '{"event": "before_tool"}'

    def test_replaces_gobby_bin_with_which(self) -> None:
        from gobby.workflows.sync import resolve_sync_placeholders

        with patch("gobby.workflows.sync_rules.shutil.which", return_value="/usr/local/bin/gobby"):
            result = resolve_sync_placeholders("run {{ gobby_bin }} tasks list")
            assert result == "run /usr/local/bin/gobby tasks list"

    def test_falls_back_to_python_m_gobby(self) -> None:
        from gobby.workflows.sync import resolve_sync_placeholders

        with patch("gobby.workflows.sync_rules.shutil.which", return_value=None):
            result = resolve_sync_placeholders("run {{ gobby_bin }} tasks")
            assert "-m gobby" in result
            assert "{{ gobby_bin }}" not in result


# ═══════════════════════════════════════════════════════════════════════
# propagate_to_installed
# ═══════════════════════════════════════════════════════════════════════


class TestPropagateToInstalled:
    """Tests for propagate_to_installed."""

    def test_propagates_definition_json_change(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.workflows.sync import propagate_to_installed

        # Create template and installed rows
        manager.create(
            name="test-rule",
            definition_json='{"old": true}',
            workflow_type="rule",
            source="template",
        )
        manager.create(
            name="test-rule",
            definition_json='{"old": true}',
            workflow_type="rule",
            source="installed",
            enabled=True,
        )

        propagate_to_installed(manager, "test-rule", '{"new": true}')

        # Verify installed copy updated
        installed_row = db.fetchone(
            "SELECT definition_json FROM workflow_definitions WHERE name = ? AND source = 'installed'",
            ("test-rule",),
        )
        assert installed_row is not None
        assert json.loads(installed_row["definition_json"]) == {"new": True}

    def test_no_installed_copy_does_nothing(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.workflows.sync import propagate_to_installed

        # No installed row - should not raise
        propagate_to_installed(manager, "nonexistent", '{"new": true}')

    def test_propagates_tags_change(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.workflows.sync import propagate_to_installed

        manager.create(
            name="tag-rule",
            definition_json='{"v": 1}',
            workflow_type="rule",
            source="template",
            tags=["gobby"],
        )
        manager.create(
            name="tag-rule",
            definition_json='{"v": 1}',
            workflow_type="rule",
            source="installed",
            tags=["old-tag"],
        )

        propagate_to_installed(manager, "tag-rule", '{"v": 1}', tags=["gobby", "new-tag"])

        installed_row = db.fetchone(
            "SELECT tags FROM workflow_definitions WHERE name = ? AND source = 'installed'",
            ("tag-rule",),
        )
        assert installed_row is not None
        tags = json.loads(installed_row["tags"])
        assert "gobby" in tags
        assert "new-tag" in tags

    def test_same_definition_same_tags_no_update(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.workflows.sync import propagate_to_installed

        manager.create(
            name="same-rule",
            definition_json='{"v": 1}',
            workflow_type="rule",
            source="installed",
        )

        # Same definition, no tags change - should not call update
        propagate_to_installed(manager, "same-rule", '{"v": 1}')


# ═══════════════════════════════════════════════════════════════════════
# ensure_tag_on_installed
# ═══════════════════════════════════════════════════════════════════════


class TestEnsureTagOnInstalled:
    """Tests for ensure_tag_on_installed."""

    def test_adds_tag_to_untagged_template(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.workflows.sync import ensure_tag_on_installed

        manager.create(
            name="untagged-rule",
            definition_json='{"v": 1}',
            workflow_type="rule",
            source="template",
            tags=[],
        )

        ensure_tag_on_installed(manager, "rule", "gobby")

        row = manager.get_by_name("untagged-rule", include_templates=True)
        assert row is not None
        assert "gobby" in (row.tags or [])

    def test_skips_rows_with_different_owner_tag(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.workflows.sync import ensure_tag_on_installed

        manager.create(
            name="user-rule",
            definition_json='{"v": 1}',
            workflow_type="rule",
            source="template",
            tags=["user"],
        )

        ensure_tag_on_installed(manager, "rule", "gobby")

        row = manager.get_by_name("user-rule", include_templates=True)
        assert row is not None
        assert "gobby" not in (row.tags or [])

    def test_skips_non_template_non_installed_sources(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        from gobby.workflows.sync import ensure_tag_on_installed

        manager.create(
            name="custom-rule",
            definition_json='{"v": 1}',
            workflow_type="rule",
            source="custom",
            tags=[],
        )

        ensure_tag_on_installed(manager, "rule", "gobby")

        row = db.fetchone(
            "SELECT tags FROM workflow_definitions WHERE name = ?",
            ("custom-rule",),
        )
        tags = json.loads(row["tags"]) if row and row["tags"] else []
        assert "gobby" not in tags


# ═══════════════════════════════════════════════════════════════════════
# sync_bundled_rules
# ═══════════════════════════════════════════════════════════════════════


class TestSyncBundledRules:
    """Tests for sync_bundled_rules edge cases."""

    def test_missing_rules_path_returns_empty_result(self, db: LocalDatabase) -> None:
        from gobby.workflows.sync import sync_bundled_rules

        result = sync_bundled_rules(db, rules_path=Path("/nonexistent/path"))
        assert result["success"] is True
        assert result["synced"] == 0

    def test_skips_non_dict_yaml(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_rules

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        rule_yaml = rules_dir / "bad.yaml"
        rule_yaml.write_text("- just a list\n- not a dict\n")

        result = sync_bundled_rules(db, rules_path=rules_dir)
        assert result["synced"] == 0

    def test_skips_yaml_without_rules_key(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_rules

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        rule_yaml = rules_dir / "no_rules.yaml"
        rule_yaml.write_text("name: test\ndescription: not a rule file\n")

        result = sync_bundled_rules(db, rules_path=rules_dir)
        assert result["skipped"] == 1

    def test_skips_deprecated_directory(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_rules

        rules_dir = tmp_path / "rules"
        deprecated_dir = rules_dir / "deprecated"
        deprecated_dir.mkdir(parents=True)
        rule_yaml = deprecated_dir / "old.yaml"
        rule_yaml.write_text(
            """
rules:
  old-rule:
    event: before_tool
    effect:
      type: log
      message: "old"
"""
        )

        result = sync_bundled_rules(db, rules_path=rules_dir)
        assert result["synced"] == 0

    def test_non_dict_rule_data_adds_error(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_rules

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        rule_yaml = rules_dir / "bad_rule.yaml"
        rule_yaml.write_text(
            """
rules:
  bad-rule: "just a string"
"""
        )

        result = sync_bundled_rules(db, rules_path=rules_dir)
        assert len(result["errors"]) == 1
        assert "bad-rule" in result["errors"][0]

    def test_user_tag_collision_skips(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_rules

        # Create a gobby template
        manager = LocalWorkflowDefinitionManager(db)
        manager.create(
            name="collision-rule",
            definition_json='{"event": "before_tool", "effects": [{"type": "log", "message": "v1"}]}',
            workflow_type="rule",
            source="template",
            tags=["gobby"],
        )

        # User-tag sync should skip this name
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        rule_yaml = rules_dir / "collision.yaml"
        rule_yaml.write_text(
            """
rules:
  collision-rule:
    event: before_tool
    effect:
      type: log
      message: "user version"
"""
        )

        result = sync_bundled_rules(db, rules_path=rules_dir, tag="user")
        assert result["skipped"] == 1

    def test_handles_yaml_parse_error(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_rules

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        rule_yaml = rules_dir / "broken.yaml"
        rule_yaml.write_text(":\n  invalid: [yaml\n  broken")

        result = sync_bundled_rules(db, rules_path=rules_dir)
        assert len(result["errors"]) >= 1


# ═══════════════════════════════════════════════════════════════════════
# sync_bundled_pipelines
# ═══════════════════════════════════════════════════════════════════════


class TestSyncBundledPipelines:
    """Tests for sync_bundled_pipelines edge cases."""

    def test_missing_path_returns_error(self, db: LocalDatabase) -> None:
        from gobby.workflows.sync import sync_bundled_pipelines

        with patch(
            "gobby.workflows.sync_pipelines.get_bundled_pipelines_path",
            return_value=Path("/nonexistent"),
        ):
            result = sync_bundled_pipelines(db)
            assert len(result["errors"]) >= 1

    def test_skips_non_dict_yaml(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_pipelines

        pip_dir = tmp_path / "pipelines"
        pip_dir.mkdir()
        (pip_dir / "bad.yaml").write_text("- a list\n")

        with patch("gobby.workflows.sync_pipelines.get_bundled_pipelines_path", return_value=pip_dir):
            result = sync_bundled_pipelines(db)
            assert result["synced"] == 0

    def test_skips_yaml_without_name(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_pipelines

        pip_dir = tmp_path / "pipelines"
        pip_dir.mkdir()
        (pip_dir / "noname.yaml").write_text("description: no name field\ntype: pipeline\n")

        with patch("gobby.workflows.sync_pipelines.get_bundled_pipelines_path", return_value=pip_dir):
            result = sync_bundled_pipelines(db)
            assert result["synced"] == 0

    def test_skips_invalid_schema(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_pipelines

        pip_dir = tmp_path / "pipelines"
        pip_dir.mkdir()
        # Invalid: steps must be a list, not a string
        (pip_dir / "invalid.yaml").write_text(
            "name: invalid-pipeline\ntype: pipeline\nsteps: not-a-list\n"
        )

        with patch("gobby.workflows.sync_pipelines.get_bundled_pipelines_path", return_value=pip_dir):
            result = sync_bundled_pipelines(db)
            assert result["synced"] == 0

    def test_syncs_valid_pipeline(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_pipelines

        pip_dir = tmp_path / "pipelines"
        pip_dir.mkdir()
        (pip_dir / "good.yaml").write_text(
            """
name: test-pipeline
type: pipeline
description: A test pipeline
steps:
  - id: step1
    exec: echo hello
"""
        )

        with patch("gobby.workflows.sync_pipelines.get_bundled_pipelines_path", return_value=pip_dir):
            result = sync_bundled_pipelines(db)
            assert result["synced"] == 1


# ═══════════════════════════════════════════════════════════════════════
# sync_bundled_variables
# ═══════════════════════════════════════════════════════════════════════


class TestSyncBundledVariables:
    """Tests for sync_bundled_variables."""

    def test_missing_path_returns_empty_result(self, db: LocalDatabase) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        result = sync_bundled_variables(db, variables_path=Path("/nonexistent"))
        assert result["success"] is True
        assert result["synced"] == 0

    def test_syncs_new_variable(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "test.yaml").write_text(
            """
variables:
  my_var:
    value: "hello"
    description: "A test variable"
"""
        )

        result = sync_bundled_variables(db, variables_path=var_dir)
        assert result["synced"] == 1

    def test_skips_non_dict_yaml(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "bad.yaml").write_text("- list item\n")

        result = sync_bundled_variables(db, variables_path=var_dir)
        assert result["synced"] == 0

    def test_skips_yaml_without_variables_key(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "no_vars.yaml").write_text("name: not variables\n")

        result = sync_bundled_variables(db, variables_path=var_dir)
        assert result["skipped"] == 1

    def test_non_dict_variable_adds_error(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "bad_var.yaml").write_text(
            """
variables:
  bad_var: "just a string"
"""
        )

        result = sync_bundled_variables(db, variables_path=var_dir)
        assert len(result["errors"]) == 1

    def test_updates_changed_variable(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        var_file = var_dir / "test.yaml"
        var_file.write_text(
            """
variables:
  update_var:
    value: "v1"
"""
        )

        sync_bundled_variables(db, variables_path=var_dir)

        var_file.write_text(
            """
variables:
  update_var:
    value: "v2"
"""
        )
        result = sync_bundled_variables(db, variables_path=var_dir)
        assert result["updated"] == 1

    def test_skips_unchanged_variable(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "same.yaml").write_text(
            """
variables:
  same_var:
    value: "constant"
"""
        )

        sync_bundled_variables(db, variables_path=var_dir)
        result = sync_bundled_variables(db, variables_path=var_dir)
        assert result["skipped"] == 1

    def test_orphan_cleanup(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        var_file = var_dir / "orphan.yaml"
        var_file.write_text(
            """
variables:
  orphan_var:
    value: "soon gone"
"""
        )

        sync_bundled_variables(db, variables_path=var_dir)
        var_file.unlink()

        result = sync_bundled_variables(db, variables_path=var_dir)
        assert result["orphaned"] >= 1

    def test_restores_soft_deleted_template(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "restore.yaml").write_text(
            """
variables:
  restore_var:
    value: "restored"
"""
        )

        sync_bundled_variables(db, variables_path=var_dir)

        manager = LocalWorkflowDefinitionManager(db)
        row = manager.get_by_name("restore_var", include_templates=True)
        assert row is not None
        manager.delete(row.id)

        result = sync_bundled_variables(db, variables_path=var_dir)
        assert result["updated"] >= 1

    def test_handles_yaml_parse_error(self, db: LocalDatabase, tmp_path: Path) -> None:
        from gobby.workflows.sync import sync_bundled_variables

        var_dir = tmp_path / "variables"
        var_dir.mkdir()
        (var_dir / "broken.yaml").write_text(":\n  invalid: [yaml\n  broken")

        result = sync_bundled_variables(db, variables_path=var_dir)
        assert len(result["errors"]) >= 1


# ═══════════════════════════════════════════════════════════════════════
# get_bundled_*_path helpers
# ═══════════════════════════════════════════════════════════════════════


class TestBundledPaths:
    """Tests for path helper functions."""

    def test_get_bundled_rules_path_returns_path(self) -> None:
        from gobby.workflows.sync import get_bundled_rules_path

        result = get_bundled_rules_path()
        assert isinstance(result, Path)
        assert str(result).endswith("rules")

    def test_get_bundled_pipelines_path_returns_path(self) -> None:
        from gobby.workflows.sync import get_bundled_pipelines_path

        result = get_bundled_pipelines_path()
        assert isinstance(result, Path)
        assert str(result).endswith("pipelines")

    def test_get_bundled_variables_path_returns_path(self) -> None:
        from gobby.workflows.sync import get_bundled_variables_path

        result = get_bundled_variables_path()
        assert isinstance(result, Path)
        assert str(result).endswith("variables")
