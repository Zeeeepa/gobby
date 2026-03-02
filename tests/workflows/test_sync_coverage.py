"""Tests for workflows/sync.py — targeting uncovered lines."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.workflows.sync import (
    _ensure_gobby_tag_on_installed,
    _propagate_to_installed,
    _sync_single_rule,
    _sync_single_variable,
    get_bundled_rules_path,
    get_bundled_variables_path,
    get_bundled_workflows_path,
    sync_bundled_rules,
    sync_bundled_variables,
    sync_bundled_workflows,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


class TestEnsureGobbyTag:
    def test_adds_gobby_tag(self):
        mgr = MagicMock()
        row = MagicMock()
        row.id = "r1"
        row.source = "template"
        row.tags = ["other"]
        mgr.list_all.return_value = [row]

        _ensure_gobby_tag_on_installed(mgr, "rule")
        mgr.update.assert_called_once_with("r1", tags=["other", "gobby"])

    def test_skips_when_tag_present(self):
        mgr = MagicMock()
        row = MagicMock()
        row.id = "r1"
        row.source = "template"
        row.tags = ["gobby", "other"]
        mgr.list_all.return_value = [row]

        _ensure_gobby_tag_on_installed(mgr, "rule")
        mgr.update.assert_not_called()

    def test_skips_non_template_sources(self):
        mgr = MagicMock()
        row = MagicMock()
        row.id = "r1"
        row.source = "project"
        row.tags = []
        mgr.list_all.return_value = [row]

        _ensure_gobby_tag_on_installed(mgr, "rule")
        mgr.update.assert_not_called()

    def test_handles_none_tags(self):
        mgr = MagicMock()
        row = MagicMock()
        row.id = "r1"
        row.source = "template"
        row.tags = None
        mgr.list_all.return_value = [row]

        _ensure_gobby_tag_on_installed(mgr, "rule")
        mgr.update.assert_called_once_with("r1", tags=["gobby"])


# ---------------------------------------------------------------------------
# sync_bundled_variables
# ---------------------------------------------------------------------------


class TestSyncBundledVariables:
    def test_path_not_exists(self):
        db = MagicMock()

        with patch(
            "gobby.workflows.sync.get_bundled_variables_path",
            return_value=Path("/nonexistent"),
        ):
            result = sync_bundled_variables(db)

        assert result["success"] is True
        assert result["synced"] == 0

    def test_create_new_variable(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            tags: [config]
            variables:
              my_var:
                value: true
                description: A test variable
        """)
        var_file = tmp_path / "vars.yaml"
        var_file.write_text(yaml_content)

        db = MagicMock()
        mgr = MagicMock()
        mgr.get_by_name.return_value = None
        mgr.list_all.return_value = []

        with (
            patch("gobby.workflows.sync.get_bundled_variables_path", return_value=tmp_path),
            patch("gobby.workflows.sync.LocalWorkflowDefinitionManager", return_value=mgr),
        ):
            db.fetchall.return_value = []
            result = sync_bundled_variables(db)

        assert result["synced"] == 1

    def test_skip_non_dict_variable(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            variables:
              bad_var: "just a string"
        """)
        var_file = tmp_path / "vars.yaml"
        var_file.write_text(yaml_content)

        db = MagicMock()
        mgr = MagicMock()
        mgr.list_all.return_value = []

        with (
            patch("gobby.workflows.sync.get_bundled_variables_path", return_value=tmp_path),
            patch("gobby.workflows.sync.LocalWorkflowDefinitionManager", return_value=mgr),
        ):
            db.fetchall.return_value = []
            result = sync_bundled_variables(db)

        assert "not a dict" in result["errors"][0]

    def test_orphan_cleanup_variables(self, tmp_path):
        db = MagicMock()
        mgr = MagicMock()
        mgr.list_all.return_value = []

        db.fetchall.return_value = [
            {"id": "orphan-v1", "name": "removed-var"},
        ]

        with (
            patch("gobby.workflows.sync.get_bundled_variables_path", return_value=tmp_path),
            patch("gobby.workflows.sync.LocalWorkflowDefinitionManager", return_value=mgr),
        ):
            result = sync_bundled_variables(db)

        assert result["orphaned"] == 1


# ---------------------------------------------------------------------------
# _sync_single_variable
# ---------------------------------------------------------------------------
