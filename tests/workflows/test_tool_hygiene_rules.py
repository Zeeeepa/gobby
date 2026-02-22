"""Tests for tool-hygiene.yaml rules.

Verifies require-uv blocks naked python/pip and track-pending-memory-review
sets a variable after file edits.
"""

from __future__ import annotations

import json

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody
from gobby.workflows.sync import sync_bundled_rules

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_tool_hygiene.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def manager(db: LocalDatabase) -> LocalWorkflowDefinitionManager:
    return LocalWorkflowDefinitionManager(db)


def _sync_bundled(db):
    """Sync bundled rules from the real rules directory."""
    from gobby.workflows.sync import get_bundled_rules_path

    return sync_bundled_rules(db, get_bundled_rules_path())


class TestToolHygieneSync:
    """Test that tool-hygiene.yaml syncs correctly."""

    def test_bundled_file_syncs_both_rules(self, db, manager) -> None:
        """Both tool-hygiene rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        assert "require-uv" in rule_names
        assert "track-pending-memory-review" in rule_names

    def test_all_rules_have_group(self, db, manager) -> None:
        """All tool-hygiene rules should have group='tool-hygiene'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in {"require-uv", "track-pending-memory-review"}:
                body = json.loads(row.definition_json)
                assert body.get("group") == "tool-hygiene", f"{row.name} missing group"

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in {"require-uv", "track-pending-memory-review"}:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                assert body.effect.type in {"block", "set_variable"}


class TestRequireUvRule:
    """Verify require-uv rule blocks naked python/pip."""

    def test_blocks_bash_tool(self, db, manager) -> None:
        """require-uv should target the Bash tool."""
        _sync_bundled(db)

        row = manager.get_by_name("require-uv")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert body.effect.tools == ["Bash"]

    def test_has_command_pattern_for_python_pip(self, db, manager) -> None:
        """require-uv should have a command pattern matching python/pip."""
        _sync_bundled(db)

        row = manager.get_by_name("require-uv")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.effect.command_pattern is not None
        assert "python" in body.effect.command_pattern
        assert "pip" in body.effect.command_pattern

    def test_has_command_not_pattern_for_uv(self, db, manager) -> None:
        """require-uv should have a not-pattern allowing uv commands."""
        _sync_bundled(db)

        row = manager.get_by_name("require-uv")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.effect.command_not_pattern is not None
        assert "uv" in body.effect.command_not_pattern

    def test_has_when_condition(self, db, manager) -> None:
        """require-uv should only fire when require_uv variable is set."""
        _sync_bundled(db)

        row = manager.get_by_name("require-uv")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "require_uv" in body.when


class TestTrackPendingMemoryReview:
    """Verify track-pending-memory-review sets variable after edits."""

    def test_is_set_variable_effect(self, db, manager) -> None:
        """track-pending-memory-review should use set_variable effect."""
        _sync_bundled(db)

        row = manager.get_by_name("track-pending-memory-review")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.type == "set_variable"

    def test_sets_pending_memory_review_variable(self, db, manager) -> None:
        """Should set the pending_memory_review variable to true."""
        _sync_bundled(db)

        row = manager.get_by_name("track-pending-memory-review")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.effect.variable == "pending_memory_review"
        assert body.effect.value is True

    def test_has_when_condition_for_edit_tools(self, db, manager) -> None:
        """Should fire on Edit, Write, NotebookEdit, or close_task."""
        _sync_bundled(db)

        row = manager.get_by_name("track-pending-memory-review")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "Edit" in body.when
        assert "Write" in body.when
