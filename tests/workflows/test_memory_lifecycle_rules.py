"""Tests for memory-lifecycle rules.

Verifies memory lifecycle rules sync correctly and have proper structure.
Rules that were merged into context-handoff (preserve-context-on-compact,
preserve-context-on-end) are tested there instead.

Active memory-lifecycle rules:
- reset-memory-tracking-on-start: set_variable on session_start
- memory-recall-on-prompt: mcp_call on before_agent
- memory-capture-nudge: inject_context on before_agent
- require-memory-review-before-close: block on before_tool (close_task)
- require-memory-review-before-needs-review: block on before_tool (mark_task_needs_review)
- require-memory-review-before-approve: block on before_tool (mark_task_review_approved)
- clear-memory-review-on-create: set_variable on before_tool

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

MEMORY_RULES = {
    "reset-memory-tracking-on-start",
    "memory-recall-on-prompt",
    "memory-capture-nudge",
    "require-memory-review-before-close",
    "require-memory-review-before-needs-review",
    "require-memory-review-before-approve",
    "clear-memory-review-on-create",
}


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_memory_lifecycle.db"
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


class TestMemoryLifecycleSync:
    """Test that memory-lifecycle rules sync correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All memory-lifecycle rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        for rule_name in MEMORY_RULES:
            assert rule_name in rule_names, f"Missing rule: {rule_name}"

    def test_all_rules_have_group(self, db, manager) -> None:
        """All memory-lifecycle rules should have group='memory-lifecycle'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in MEMORY_RULES:
                body = json.loads(row.definition_json)
                assert body.get("group") == "memory-lifecycle", f"{row.name} missing group"

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in MEMORY_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                for effect in body.resolved_effects:
                    assert effect.type in {
                        "set_variable",
                        "inject_context",
                        "mcp_call",
                        "block",
                    }


# ═══════════════════════════════════════════════════════════════════════
# reset-memory-tracking-on-start
# ═══════════════════════════════════════════════════════════════════════


class TestResetMemoryTrackingOnStart:
    """Reset injected_memory_ids on context loss (session_start)."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("reset-memory-tracking-on-start", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effects[0].type == "set_variable"
        assert body.effects[0].variable == "injected_memory_ids"

    def test_has_when_condition(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("reset-memory-tracking-on-start", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "clear" in body.when
        assert "compact" in body.when


# ═══════════════════════════════════════════════════════════════════════
# memory-recall-on-prompt
# ═══════════════════════════════════════════════════════════════════════


class TestMemoryRecallOnPrompt:
    """Recall relevant memories before agent prompt."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("memory-recall-on-prompt", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_agent"
        assert body.effects[0].type == "mcp_call"
        assert body.effects[0].server == "gobby-memory"
        assert body.effects[0].tool == "search_memories"

    def test_not_background(self, db, manager) -> None:
        """Recall must block to inject context."""
        _sync_bundled(db)
        row = manager.get_by_name("memory-recall-on-prompt", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.effects[0].background is False


# ═══════════════════════════════════════════════════════════════════════
# memory-capture-nudge
# ═══════════════════════════════════════════════════════════════════════


class TestMemoryCaptureNudge:
    """Nudge agent to save user preferences."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("memory-capture-nudge", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_agent"
        assert body.effects[0].type == "inject_context"
        assert body.effects[0].template is not None
        assert "create_memory" in body.effects[0].template

    def test_has_when_condition(self, db, manager) -> None:
        """Only nudge on substantial prompts (not slash commands)."""
        _sync_bundled(db)
        row = manager.get_by_name("memory-capture-nudge", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "prompt" in body.when


# ═══════════════════════════════════════════════════════════════════════
# require-memory-review-before-close
# ═══════════════════════════════════════════════════════════════════════


class TestRequireMemoryReviewBeforeClose:
    """Gate task close until agent reviews memories."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("require-memory-review-before-close", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effects[0].type == "block"
        assert body.effects[0].reason is not None
        assert "create_memory" in body.effects[0].reason

    def test_has_when_condition(self, db, manager) -> None:
        """Only block close_task with commit_sha when pending_memory_review is set."""
        _sync_bundled(db)
        row = manager.get_by_name("require-memory-review-before-close", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "close_task" in body.when
        assert "pending_memory_review" in body.when
        assert "commit_sha" in body.when


# ═══════════════════════════════════════════════════════════════════════
# require-memory-review-before-needs-review
# ═══════════════════════════════════════════════════════════════════════


class TestRequireMemoryReviewBeforeNeedsReview:
    """Gate mark_task_needs_review until agent reviews memories."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name(
            "require-memory-review-before-needs-review", include_templates=True
        )
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effects[0].type == "block"
        assert body.effects[0].reason is not None

    def test_has_when_condition(self, db, manager) -> None:
        """Only block mark_task_needs_review when pending_memory_review is set."""
        _sync_bundled(db)
        row = manager.get_by_name(
            "require-memory-review-before-needs-review", include_templates=True
        )
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "mark_task_needs_review" in body.when
        assert "pending_memory_review" in body.when
        assert "commit_sha" not in body.when


# ═══════════════════════════════════════════════════════════════════════
# require-memory-review-before-approve
# ═══════════════════════════════════════════════════════════════════════


class TestRequireMemoryReviewBeforeApprove:
    """Gate mark_task_review_approved until agent reviews memories."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("require-memory-review-before-approve", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effects[0].type == "block"
        assert body.effects[0].reason is not None

    def test_has_when_condition(self, db, manager) -> None:
        """Only block mark_task_review_approved when pending_memory_review is set."""
        _sync_bundled(db)
        row = manager.get_by_name("require-memory-review-before-approve", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "mark_task_review_approved" in body.when
        assert "pending_memory_review" in body.when
        assert "commit_sha" not in body.when


# ═══════════════════════════════════════════════════════════════════════
# clear-memory-review-on-create
# ═══════════════════════════════════════════════════════════════════════


class TestClearMemoryReviewOnCreate:
    """Clear pending_memory_review flag when create_memory is called."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("clear-memory-review-on-create", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effects[0].type == "set_variable"
        assert body.effects[0].variable == "pending_memory_review"
        assert body.effects[0].value is False

    def test_has_when_condition(self, db, manager) -> None:
        """Must match create_memory on gobby-memory server."""
        _sync_bundled(db)
        row = manager.get_by_name("clear-memory-review-on-create", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "create_memory" in body.when
        assert "gobby-memory" in body.when
