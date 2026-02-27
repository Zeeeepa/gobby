"""Tests for stop-gates rules.

Verifies stop attempt counting, stop blocking gates (tool block,
error triage, task close), and per-turn/per-tool resets via multi-effect rules.
"""

from __future__ import annotations

import json

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody
from gobby.workflows.safe_evaluator import SafeExpressionEvaluator
from gobby.workflows.sync import sync_bundled_rules

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_stop_gates.db"
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


def _get_rule(manager, name):
    """Get a bundled rule by name (templates included since bundled rules are templates)."""
    return manager.get_by_name(name, include_templates=True)


STOP_GATES_RULES = {
    "increment-stop-attempts",
    "block-stop-after-tool-block",
    "require-error-triage",
    "require-task-close",
    "reset-stop-cycle-on-prompt",
}


class TestStopGatesSync:
    """Test that stop-gates rules sync correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All stop-gates rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        assert STOP_GATES_RULES.issubset(rule_names), (
            f"Missing: {STOP_GATES_RULES - rule_names}"
        )

    def test_all_rules_have_group(self, db, manager) -> None:
        """All rules should have group='stop-gates'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in STOP_GATES_RULES:
                body = json.loads(row.definition_json)
                assert body.get("group") == "stop-gates", (
                    f"{row.name} missing group"
                )

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in STOP_GATES_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                for effect in body.resolved_effects:
                    assert effect.type in {"block", "set_variable"}


class TestIncrementStopAttempts:
    """Verify increment-stop-attempts counts stop attempts."""

    def test_is_stop_event(self, db, manager) -> None:
        """Should fire on stop event."""
        _sync_bundled(db)

        row = _get_rule(manager, "increment-stop-attempts")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "stop_attempts"

    def test_no_when_condition(self, db, manager) -> None:
        """Should always fire (no when condition)."""
        _sync_bundled(db)

        row = _get_rule(manager, "increment-stop-attempts")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is None


class TestBlockStopAfterToolBlock:
    """Verify block-stop-after-tool-block blocks stop when tool was blocked.

    The rule is self-clearing: it clears tool_block_pending when it fires,
    so it only blocks once per tool block (no 3-attempt loop).
    """

    def test_blocks_on_stop(self, db, manager) -> None:
        """Should have a block effect on stop event."""
        _sync_bundled(db)

        row = _get_rule(manager, "block-stop-after-tool-block")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"

        effects = body.resolved_effects
        effect_types = [e.type for e in effects]
        assert "block" in effect_types

    def test_self_clearing(self, db, manager) -> None:
        """Should clear tool_block_pending when it fires (self-clearing gate)."""
        _sync_bundled(db)

        row = _get_rule(manager, "block-stop-after-tool-block")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        effects = body.resolved_effects
        set_var_effects = [e for e in effects if e.type == "set_variable"]
        assert len(set_var_effects) == 1
        assert set_var_effects[0].variable == "tool_block_pending"
        assert set_var_effects[0].value is False

    def test_when_checks_tool_block_pending(self, db, manager) -> None:
        """Should check tool_block_pending only (no stop_attempts check)."""
        _sync_bundled(db)

        row = _get_rule(manager, "block-stop-after-tool-block")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "tool_block_pending" in body.when
        assert "stop_attempts" not in body.when


class TestRequireErrorTriage:
    """Verify require-error-triage blocks stop until triage confirmed."""

    def test_blocks_on_stop(self, db, manager) -> None:
        """Should be a block effect on stop event."""
        _sync_bundled(db)

        row = _get_rule(manager, "require-error-triage")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "block"

    def test_when_checks_triage_flag(self, db, manager) -> None:
        """Should check pre_existing_errors_triaged and task_has_commits."""
        _sync_bundled(db)

        row = _get_rule(manager, "require-error-triage")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "pre_existing_errors_triaged" in body.when
        assert "task_has_commits" in body.when


class TestRequireTaskClose:
    """Verify require-task-close blocks stop if task in_progress."""

    def test_blocks_on_stop(self, db, manager) -> None:
        """Should be a block effect on stop event."""
        _sync_bundled(db)

        row = _get_rule(manager, "require-task-close")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "block"

    def test_when_checks_mode_level_and_task(self, db, manager) -> None:
        """Should check mode_level and task_claimed."""
        _sync_bundled(db)

        row = _get_rule(manager, "require-task-close")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "mode_level" in body.when
        assert "task_claimed" in body.when

    def test_does_not_block_when_task_claimed_unset(self, db, manager) -> None:
        """Should NOT block when task_claimed was never set (no false positive)."""
        _sync_bundled(db)

        row = _get_rule(manager, "require-task-close")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        variables: dict[str, object] = {"mode_level": 2, "stop_attempts": 1}
        evaluator = SafeExpressionEvaluator(
            context={"variables": variables},
            allowed_funcs={"len": len, "str": str, "int": int, "bool": bool},
        )
        assert not evaluator.evaluate(body.when), (
            "Rule should not fire when task_claimed is unset"
        )

    def test_blocks_when_task_claimed_is_set(self, db, manager) -> None:
        """Should block when task_claimed is set and conditions met."""
        _sync_bundled(db)

        row = _get_rule(manager, "require-task-close")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        variables: dict[str, object] = {
            "mode_level": 2,
            "stop_attempts": 1,
            "task_claimed": True,
            "claimed_task_id": "task-123",
        }
        evaluator = SafeExpressionEvaluator(
            context={"variables": variables},
            allowed_funcs={"len": len, "str": str, "int": int, "bool": bool},
        )
        assert evaluator.evaluate(body.when), (
            "Rule should fire when task_claimed is set"
        )


class TestResetStopCycleOnPrompt:
    """Verify reset-stop-cycle-on-prompt multi-effect rule.

    Merges clear-tool-block-on-prompt + reset-error-triage-on-prompt.
    No when guard — fires on every before_agent event. This is safe because
    block-stop-after-tool-block is self-clearing (clears tool_block_pending
    when it fires), so there's no risk of premature reset breaking an
    escape hatch.
    """

    def test_no_reset_stop_attempts_on_prompt(self, db, manager) -> None:
        """stop_attempts should NOT be reset on before_agent.

        It's reset by the rule engine's auto-clear on successful after_tool.
        """
        _sync_bundled(db)

        row = _get_rule(manager, "reset-stop-attempts-on-prompt")
        assert row is None, "reset-stop-attempts-on-prompt should not exist"

    def test_clears_both_flags(self, db, manager) -> None:
        """Should clear tool_block_pending and pre_existing_errors_triaged."""
        _sync_bundled(db)

        row = _get_rule(manager, "reset-stop-cycle-on-prompt")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_agent"

        effects = body.resolved_effects
        assert len(effects) == 2
        vars_and_values = {e.variable: e.value for e in effects}
        assert vars_and_values["tool_block_pending"] is False
        assert vars_and_values["pre_existing_errors_triaged"] is False

    def test_no_when_guard(self, db, manager) -> None:
        """Should fire unconditionally (no when condition)."""
        _sync_bundled(db)

        row = _get_rule(manager, "reset-stop-cycle-on-prompt")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is None


