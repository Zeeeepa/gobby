"""Tests for plan-mode rules.

Verifies plan-mode detection (enter/exit via multi-effect rules),
mode_level tracking, and session_start reset all work correctly.
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

    result = sync_bundled_rules(db, get_bundled_rules_path())
    # Mark templates as installed so get_by_name() finds them without include_templates
    db.execute("UPDATE workflow_definitions SET source = 'installed' WHERE source = 'template'")
    return result


PLAN_MODE_RULES = {
    "handle-plan-mode-entry",
    "handle-plan-mode-exit",
    "reset-plan-mode-on-session-start",
}


class TestPlanModeSync:
    """Test that plan-mode rules sync correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All 3 plan-mode rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        assert PLAN_MODE_RULES.issubset(rule_names), f"Missing: {PLAN_MODE_RULES - rule_names}"

    def test_all_rules_have_group(self, db, manager) -> None:
        """All plan-mode rules should have group='plan-mode'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in PLAN_MODE_RULES:
                body = json.loads(row.definition_json)
                assert body.get("group") == "plan-mode", f"{row.name} missing group"

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in PLAN_MODE_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                for effect in body.resolved_effects:
                    assert effect.type == "set_variable"


class TestHandlePlanModeEntry:
    """Verify handle-plan-mode-entry multi-effect rule."""

    def test_sets_plan_mode_and_mode_level(self, db, manager) -> None:
        """Should set plan_mode=true and mode_level=0 on EnterPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("handle-plan-mode-entry")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        effects = body.resolved_effects
        assert len(effects) == 2
        assert effects[0].variable == "plan_mode"
        assert effects[0].value is True
        assert effects[1].variable == "mode_level"
        assert effects[1].value == 0

    def test_when_condition_matches_enter_plan_mode(self, db, manager) -> None:
        """Should fire when tool_name is EnterPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("handle-plan-mode-entry")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "EnterPlanMode" in body.when


class TestHandlePlanModeExit:
    """Verify handle-plan-mode-exit multi-effect rule."""

    def test_sets_plan_mode_false_and_restores_mode_level(self, db, manager) -> None:
        """Should set plan_mode=false and restore mode_level on ExitPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("handle-plan-mode-exit")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        effects = body.resolved_effects
        assert len(effects) == 2
        assert effects[0].variable == "plan_mode"
        assert effects[0].value is False
        assert effects[1].variable == "mode_level"
        # The value is a template expression that maps chat_mode to mode_level
        assert isinstance(effects[1].value, str)
        assert "chat_mode" in effects[1].value

    def test_when_condition_matches_exit_plan_mode(self, db, manager) -> None:
        """Should fire when tool_name is ExitPlanMode."""
        _sync_bundled(db)

        row = manager.get_by_name("handle-plan-mode-exit")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "ExitPlanMode" in body.when


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
