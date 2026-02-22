"""Tests for plan-mode.yaml rules.

Verifies plan-mode detection (enter/exit), mode_level tracking,
and session_start reset all work correctly.
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
    db_path = tmp_path / "test_plan_mode.db"
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


class TestPlanModeSync:
    """Test that plan-mode.yaml syncs correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All 5 plan-mode rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        expected = {
            "detect-plan-mode-enter",
            "set-mode-level-on-enter",
            "detect-plan-mode-exit",
            "restore-mode-level-on-exit",
            "reset-plan-mode-on-session-start",
        }
        assert expected.issubset(rule_names), f"Missing: {expected - rule_names}"

    def test_all_rules_have_group(self, db, manager) -> None:
        """All plan-mode rules should have group='plan-mode'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        plan_mode_names = {
            "detect-plan-mode-enter",
            "set-mode-level-on-enter",
            "detect-plan-mode-exit",
            "restore-mode-level-on-exit",
            "reset-plan-mode-on-session-start",
        }
        for row in rules:
            if row.name in plan_mode_names:
                body = json.loads(row.definition_json)
                assert body.get("group") == "plan-mode", f"{row.name} missing group"

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        plan_mode_names = {
            "detect-plan-mode-enter",
            "set-mode-level-on-enter",
            "detect-plan-mode-exit",
            "restore-mode-level-on-exit",
            "reset-plan-mode-on-session-start",
        }
        for row in rules:
            if row.name in plan_mode_names:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                assert body.effect.type == "set_variable"


class TestDetectPlanModeEnter:
    """Verify detect-plan-mode-enter sets plan_mode=true."""

    def test_sets_plan_mode_on_enter(self, db, manager) -> None:
        """Should set plan_mode to true on EnterPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("detect-plan-mode-enter")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "plan_mode"
        assert body.effect.value is True

    def test_when_condition_matches_enter_plan_mode(self, db, manager) -> None:
        """Should fire when tool_name is EnterPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("detect-plan-mode-enter")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "EnterPlanMode" in body.when


class TestSetModeLevelOnEnter:
    """Verify set-mode-level-on-enter sets mode_level=0."""

    def test_sets_mode_level_zero(self, db, manager) -> None:
        """Should set mode_level to 0 on EnterPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("set-mode-level-on-enter")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.variable == "mode_level"
        assert body.effect.value == 0

    def test_higher_priority_than_detect(self, db, manager) -> None:
        """set-mode-level-on-enter should have higher priority number (runs after detect)."""
        _sync_bundled(db)

        detect = manager.get_by_name("detect-plan-mode-enter")
        set_level = manager.get_by_name("set-mode-level-on-enter")

        assert detect is not None
        assert set_level is not None
        assert set_level.priority >= detect.priority


class TestDetectPlanModeExit:
    """Verify detect-plan-mode-exit sets plan_mode=false."""

    def test_sets_plan_mode_false_on_exit(self, db, manager) -> None:
        """Should set plan_mode to false on ExitPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("detect-plan-mode-exit")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.variable == "plan_mode"
        assert body.effect.value is False

    def test_when_condition_matches_exit_plan_mode(self, db, manager) -> None:
        """Should fire when tool_name is ExitPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("detect-plan-mode-exit")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "ExitPlanMode" in body.when


class TestRestoreModeLevelOnExit:
    """Verify restore-mode-level-on-exit restores mode_level from chat_mode."""

    def test_sets_mode_level_variable(self, db, manager) -> None:
        """Should set mode_level variable on ExitPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("restore-mode-level-on-exit")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.variable == "mode_level"

    def test_value_uses_chat_mode_mapping(self, db, manager) -> None:
        """Value should reference chat_mode for determining mode_level."""
        _sync_bundled(db)

        row = manager.get_by_name("restore-mode-level-on-exit")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        # The value is a template expression that maps chat_mode to mode_level
        value = body.effect.value
        assert isinstance(value, str)
        assert "chat_mode" in value


class TestResetPlanModeOnSessionStart:
    """Verify reset-plan-mode-on-session-start clears plan_mode."""

    def test_resets_plan_mode_on_session_start(self, db, manager) -> None:
        """Should set plan_mode to false on session_start."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-plan-mode-on-session-start")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.variable == "plan_mode"
        assert body.effect.value is False

    def test_when_condition_covers_clear_compact_startup(self, db, manager) -> None:
        """Should fire on clear, compact, and startup sources."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-plan-mode-on-session-start")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "clear" in body.when
        assert "compact" in body.when
        assert "startup" in body.when
