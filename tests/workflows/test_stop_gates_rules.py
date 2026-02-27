"""Tests for stop-gates rules.

Verifies stop attempt counting, stop blocking gates (tool block,
error triage, task close), per-turn/per-tool resets via multi-effect rules,
and hardcoded plumbing in the rule engine for tool-error stop blocking.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody
from gobby.workflows.rule_engine import RuleEngine
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
    "block-stop-awaiting-tool-use",
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


def _make_event(
    event_type: HookEventType,
    data: dict | None = None,
    metadata: dict | None = None,
) -> HookEvent:
    """Helper to create HookEvent for rule engine tests."""
    return HookEvent(
        event_type=event_type,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data or {},
        metadata=metadata or {},
    )


class TestToolBlockPendingPlumbing:
    """Test hardcoded plumbing in RuleEngine for tool-error stop blocking.

    These behaviors are baked into evaluate() — no installed rules required.
    """

    @pytest.mark.asyncio
    async def test_after_tool_failure_sets_tool_block_pending(self, db) -> None:
        """Failed after_tool should auto-set tool_block_pending=True."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Edit", "is_error": True},
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("tool_block_pending") is True

    @pytest.mark.asyncio
    async def test_after_tool_failure_via_metadata(self, db) -> None:
        """Failed after_tool via metadata.is_failure should also set flag."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Edit"},
            metadata={"is_failure": True},
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("tool_block_pending") is True

    @pytest.mark.asyncio
    async def test_successful_after_tool_clears_tool_block_pending(self, db) -> None:
        """Successful after_tool should clear tool_block_pending."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"tool_block_pending": True}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("tool_block_pending") is False

    @pytest.mark.asyncio
    async def test_stop_blocked_when_tool_block_pending(self, db) -> None:
        """Stop should be blocked when tool_block_pending is true."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"tool_block_pending": True}

        event = _make_event(HookEventType.STOP)
        response = await engine.evaluate(event, "sess-1", variables)

        assert response.decision == "block"
        assert "tool just failed" in response.reason.lower()

    @pytest.mark.asyncio
    async def test_stop_block_is_self_clearing(self, db) -> None:
        """After blocking stop, tool_block_pending should be cleared."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"tool_block_pending": True}

        event = _make_event(HookEventType.STOP)
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("tool_block_pending") is False

    @pytest.mark.asyncio
    async def test_stop_allowed_without_tool_block_pending(self, db) -> None:
        """Stop should be allowed when tool_block_pending is not set."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        event = _make_event(HookEventType.STOP)
        response = await engine.evaluate(event, "sess-1", variables)

        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_full_cycle_failure_then_stop_then_recovery(self, db) -> None:
        """End-to-end: tool fails → stop blocked → tool succeeds → stop allowed."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        # 1. Tool fails
        fail_event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Edit", "is_error": True},
        )
        await engine.evaluate(fail_event, "sess-1", variables)
        assert variables.get("tool_block_pending") is True

        # 2. Stop is blocked (and self-clears)
        stop_event = _make_event(HookEventType.STOP)
        response = await engine.evaluate(stop_event, "sess-1", variables)
        assert response.decision == "block"
        assert variables.get("tool_block_pending") is False

        # 3. Tool succeeds
        ok_event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )
        await engine.evaluate(ok_event, "sess-1", variables)

        # 4. Stop is allowed
        response = await engine.evaluate(stop_event, "sess-1", variables)
        assert response.decision == "allow"


class TestBlockStopAwaitingToolUse:
    """Verify block-stop-awaiting-tool-use rule (static checks)."""

    def test_syncs_correctly(self, db, manager) -> None:
        """Rule should sync to workflow_definitions."""
        _sync_bundled(db)

        row = _get_rule(manager, "block-stop-awaiting-tool-use")
        assert row is not None

    def test_is_stop_event_with_correct_priority(self, db, manager) -> None:
        """Should fire on stop event with priority 12."""
        _sync_bundled(db)

        row = _get_rule(manager, "block-stop-awaiting-tool-use")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.event.value == "stop"
        assert row.priority == 12

    def test_when_references_awaiting_tool_use_and_stop_attempts(self, db, manager) -> None:
        """When condition should check awaiting_tool_use and stop_attempts."""
        _sync_bundled(db)

        row = _get_rule(manager, "block-stop-awaiting-tool-use")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "awaiting_tool_use" in body.when
        assert "stop_attempts" in body.when

    def test_has_block_effect(self, db, manager) -> None:
        """Should have a block effect."""
        _sync_bundled(db)

        row = _get_rule(manager, "block-stop-awaiting-tool-use")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        effects = body.resolved_effects
        effect_types = [e.type for e in effects]
        assert "block" in effect_types


class TestAwaitingToolUsePlumbing:
    """Test hardcoded awaiting_tool_use plumbing in RuleEngine.

    awaiting_tool_use is set on before_agent (new prompt) and cleared
    on successful after_tool. Failed after_tool does NOT clear it.
    """

    @pytest.mark.asyncio
    async def test_before_agent_sets_awaiting_tool_use(self, db) -> None:
        """before_agent should set awaiting_tool_use=True."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        event = _make_event(HookEventType.BEFORE_AGENT)
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("awaiting_tool_use") is True

    @pytest.mark.asyncio
    async def test_successful_after_tool_clears_awaiting(self, db) -> None:
        """Successful after_tool should clear awaiting_tool_use."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"awaiting_tool_use": True}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("awaiting_tool_use") is False

    @pytest.mark.asyncio
    async def test_failed_after_tool_does_not_clear_awaiting(self, db) -> None:
        """Failed after_tool should NOT clear awaiting_tool_use."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"awaiting_tool_use": True}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Edit", "is_error": True},
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("awaiting_tool_use") is True

    @pytest.mark.asyncio
    async def test_full_cycle_prompt_to_tool_success(self, db) -> None:
        """Full cycle: prompt sets awaiting → tool succeeds → awaiting cleared."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        # 1. New prompt
        prompt_event = _make_event(HookEventType.BEFORE_AGENT)
        await engine.evaluate(prompt_event, "sess-1", variables)
        assert variables.get("awaiting_tool_use") is True

        # 2. Tool succeeds
        ok_event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )
        await engine.evaluate(ok_event, "sess-1", variables)
        assert variables.get("awaiting_tool_use") is False

    @pytest.mark.asyncio
    async def test_failed_tool_keeps_awaiting_until_success(self, db) -> None:
        """Failed tools don't clear awaiting — only success does."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        # 1. New prompt
        prompt_event = _make_event(HookEventType.BEFORE_AGENT)
        await engine.evaluate(prompt_event, "sess-1", variables)
        assert variables.get("awaiting_tool_use") is True

        # 2. Tool fails — awaiting stays
        fail_event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Edit", "is_error": True},
        )
        await engine.evaluate(fail_event, "sess-1", variables)
        assert variables.get("awaiting_tool_use") is True

        # 3. Tool succeeds — awaiting clears
        ok_event = _make_event(
            HookEventType.AFTER_TOOL,
            data={"tool_name": "Read"},
        )
        await engine.evaluate(ok_event, "sess-1", variables)
        assert variables.get("awaiting_tool_use") is False


class TestForceAllowStop:
    """Test force_allow_stop catastrophic failure bypass.

    force_allow_stop bypasses all stop gates (including tool_block_pending)
    and is self-clearing after one use.
    """

    @pytest.mark.asyncio
    async def test_force_allow_stop_bypasses_stop_gates(self, db) -> None:
        """force_allow_stop should allow stop even with tool_block_pending."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {
            "force_allow_stop": True,
            "tool_block_pending": True,
        }

        event = _make_event(HookEventType.STOP)
        response = await engine.evaluate(event, "sess-1", variables)

        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_force_allow_stop_is_self_clearing(self, db) -> None:
        """force_allow_stop should be cleared after use."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"force_allow_stop": True}

        event = _make_event(HookEventType.STOP)
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("force_allow_stop") is False

    @pytest.mark.asyncio
    async def test_force_allow_stop_only_works_once(self, db) -> None:
        """Second stop after force_allow_stop should use normal logic."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {
            "force_allow_stop": True,
            "tool_block_pending": True,
        }

        event = _make_event(HookEventType.STOP)

        # First stop — force allowed
        response = await engine.evaluate(event, "sess-1", variables)
        assert response.decision == "allow"

        # Re-set tool_block_pending (force_allow_stop is cleared now)
        variables["tool_block_pending"] = True

        # Second stop — normal blocking applies
        response = await engine.evaluate(event, "sess-1", variables)
        assert response.decision == "block"

    @pytest.mark.asyncio
    async def test_catastrophic_failure_sets_force_allow_stop(self, db) -> None:
        """Tool failure with catastrophic pattern should set force_allow_stop."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"awaiting_tool_use": True}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={
                "tool_name": "Bash",
                "is_error": True,
                "tool_output": "Error: You are out of usage for this billing period.",
            },
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("force_allow_stop") is True
        assert variables.get("awaiting_tool_use") is False

    @pytest.mark.asyncio
    async def test_catastrophic_rate_limit_detected(self, db) -> None:
        """Rate limit errors should trigger catastrophic bypass."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={
                "tool_name": "Bash",
                "is_error": True,
                "tool_output": "429 Too Many Requests: rate limit exceeded",
            },
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("force_allow_stop") is True

    @pytest.mark.asyncio
    async def test_normal_failure_does_not_set_force_allow_stop(self, db) -> None:
        """Normal tool failure should NOT set force_allow_stop."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {}

        event = _make_event(
            HookEventType.AFTER_TOOL,
            data={
                "tool_name": "Edit",
                "is_error": True,
                "tool_output": "Error: old_string not found in file",
            },
        )
        await engine.evaluate(event, "sess-1", variables)

        assert variables.get("force_allow_stop") is not True

    @pytest.mark.asyncio
    async def test_catastrophic_then_stop_allowed(self, db) -> None:
        """End-to-end: catastrophic failure → stop is force-allowed."""
        engine = RuleEngine(db)
        variables: dict[str, object] = {"awaiting_tool_use": True}

        # 1. Catastrophic failure
        fail_event = _make_event(
            HookEventType.AFTER_TOOL,
            data={
                "tool_name": "Bash",
                "is_error": True,
                "tool_output": "quota exceeded — upgrade your plan",
            },
        )
        await engine.evaluate(fail_event, "sess-1", variables)
        assert variables.get("force_allow_stop") is True

        # 2. Stop is allowed (bypasses tool_block_pending too)
        stop_event = _make_event(HookEventType.STOP)
        response = await engine.evaluate(stop_event, "sess-1", variables)
        assert response.decision == "allow"
        assert variables.get("force_allow_stop") is False
