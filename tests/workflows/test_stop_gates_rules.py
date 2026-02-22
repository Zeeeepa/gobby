"""Tests for stop-gates.yaml rules.

Verifies stop attempt counting, stop blocking gates (tool block,
error triage, memory review, task close), and per-turn/per-tool resets.
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


STOP_GATES_RULES = {
    "increment-stop-attempts",
    "block-stop-after-tool-block",
    "require-error-triage",
    "memory-review-gate",
    "require-task-close",
    "clear-tool-block-on-prompt",
    "reset-error-triage-on-prompt",
    "reset-stop-on-native-tool",
    "clear-tool-block-on-tool",
}


class TestStopGatesSync:
    """Test that stop-gates.yaml syncs correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All 9 stop-gates rules should sync to workflow_definitions."""
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
                assert body.effect.type in {"block", "set_variable"}


class TestIncrementStopAttempts:
    """Verify increment-stop-attempts counts stop attempts."""

    def test_is_stop_event(self, db, manager) -> None:
        """Should fire on stop event."""
        _sync_bundled(db)

        row = manager.get_by_name("increment-stop-attempts")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "stop_attempts"

    def test_no_when_condition(self, db, manager) -> None:
        """Should always fire (no when condition)."""
        _sync_bundled(db)

        row = manager.get_by_name("increment-stop-attempts")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is None


class TestBlockStopAfterToolBlock:
    """Verify block-stop-after-tool-block blocks stop when tool was blocked."""

    def test_blocks_on_stop(self, db, manager) -> None:
        """Should be a block effect on stop event."""
        _sync_bundled(db)

        row = manager.get_by_name("block-stop-after-tool-block")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "block"

    def test_when_checks_tool_block_pending(self, db, manager) -> None:
        """Should check _tool_block_pending and stop_attempts."""
        _sync_bundled(db)

        row = manager.get_by_name("block-stop-after-tool-block")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "_tool_block_pending" in body.when
        assert "stop_attempts" in body.when


class TestRequireErrorTriage:
    """Verify require-error-triage blocks stop until triage confirmed."""

    def test_blocks_on_stop(self, db, manager) -> None:
        """Should be a block effect on stop event."""
        _sync_bundled(db)

        row = manager.get_by_name("require-error-triage")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "block"

    def test_when_checks_triage_flag(self, db, manager) -> None:
        """Should check pre_existing_errors_triaged and task_has_commits."""
        _sync_bundled(db)

        row = manager.get_by_name("require-error-triage")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "pre_existing_errors_triaged" in body.when
        assert "task_has_commits" in body.when


class TestMemoryReviewGate:
    """Verify memory-review-gate blocks stop for memory review."""

    def test_blocks_on_stop(self, db, manager) -> None:
        """Should be a block effect on stop event."""
        _sync_bundled(db)

        row = manager.get_by_name("memory-review-gate")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "block"

    def test_when_checks_pending_memory_review(self, db, manager) -> None:
        """Should check pending_memory_review."""
        _sync_bundled(db)

        row = manager.get_by_name("memory-review-gate")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "pending_memory_review" in body.when


class TestRequireTaskClose:
    """Verify require-task-close blocks stop if task in_progress."""

    def test_blocks_on_stop(self, db, manager) -> None:
        """Should be a block effect on stop event."""
        _sync_bundled(db)

        row = manager.get_by_name("require-task-close")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "stop"
        assert body.effect.type == "block"

    def test_when_checks_mode_level_and_task(self, db, manager) -> None:
        """Should check mode_level and task_claimed."""
        _sync_bundled(db)

        row = manager.get_by_name("require-task-close")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "mode_level" in body.when
        assert "task_claimed" in body.when


class TestBeforeAgentResets:
    """Verify before_agent reset rules clear state on genuine new prompt.

    These rules are gated by stop_attempts == 0 to avoid resetting state
    during stop cycles (where before_agent fires for hook feedback, not
    genuine user prompts). stop_attempts itself is only reset by
    reset-stop-on-native-tool (after_tool) to preserve the escape hatch.
    """

    def test_no_reset_stop_attempts_on_prompt(self, db, manager) -> None:
        """stop_attempts should NOT be reset on before_agent.

        It's only reset by reset-stop-on-native-tool (after_tool).
        Resetting on before_agent would break the escape hatch because
        stop-hook feedback triggers before_agent.
        """
        _sync_bundled(db)

        row = manager.get_by_name("reset-stop-attempts-on-prompt")
        assert row is None, "reset-stop-attempts-on-prompt should not exist"

    def test_clear_tool_block_gated_by_stop_cycle(self, db, manager) -> None:
        """Should clear _tool_block_pending only when not in stop cycle."""
        _sync_bundled(db)

        row = manager.get_by_name("clear-tool-block-on-prompt")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_agent"
        assert body.effect.variable == "_tool_block_pending"
        assert body.effect.value is False
        assert body.when is not None
        assert "stop_attempts" in body.when

    def test_reset_error_triage_gated_by_stop_cycle(self, db, manager) -> None:
        """Should reset pre_existing_errors_triaged only when not in stop cycle."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-error-triage-on-prompt")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_agent"
        assert body.effect.variable == "pre_existing_errors_triaged"
        assert body.effect.value is False
        assert body.when is not None
        assert "stop_attempts" in body.when


class TestAfterToolResets:
    """Verify after_tool reset rules clear state on tool use."""

    def test_reset_stop_on_native_tool(self, db, manager) -> None:
        """Should reset stop_attempts on non-MCP tool use."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-stop-on-native-tool")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.variable == "stop_attempts"
        assert body.effect.value == 0
        assert body.when is not None
        assert "mcp_tool" in body.when

    def test_clear_tool_block_on_tool(self, db, manager) -> None:
        """Should clear _tool_block_pending on any tool use."""
        _sync_bundled(db)

        row = manager.get_by_name("clear-tool-block-on-tool")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.variable == "_tool_block_pending"
        assert body.effect.value is False
        assert body.when is None  # fires on all tools
