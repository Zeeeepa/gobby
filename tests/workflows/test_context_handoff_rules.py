"""Tests for context-handoff.yaml rules.

Verifies context handoff rules sync correctly and have proper structure:
- clear-pending-context-reset-on-start: set_variable on session_start
- capture-baseline-dirty-files-on-start: mcp_call on session_start
- inject-previous-session-summary: inject_context on session_start
- inject-compact-handoff: inject_context on session_start
- task-sync-import-on-start: mcp_call on session_start
- inject-skills-on-start: inject_context on session_start
- inject-task-context-on-start: inject_context on session_start
- inject-error-triage-policy: inject_context on session_start
- generate-handoff-on-end: mcp_call on session_end
- task-sync-export-on-end: mcp_call on session_end
- set-pending-context-reset-on-compact: set_variable on pre_compact
- extract-handoff-context-on-compact: mcp_call on pre_compact
- task-sync-export-on-compact: mcp_call on pre_compact
- generate-handoff-on-compact: mcp_call on pre_compact
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

CONTEXT_HANDOFF_RULES = {
    "clear-pending-context-reset-on-start",
    "capture-baseline-dirty-files-on-start",
    "inject-previous-session-summary",
    "inject-compact-handoff",
    "task-sync-import-on-start",
    "inject-skills-on-start",
    "inject-task-context-on-start",
    "inject-error-triage-policy",
    "generate-handoff-on-end",
    "task-sync-export-on-end",
    "set-pending-context-reset-on-compact",
    "extract-handoff-context-on-compact",
    "task-sync-export-on-compact",
    "generate-handoff-on-compact",
}


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_context_handoff.db"
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


class TestContextHandoffSync:
    """Test that context-handoff.yaml syncs correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All 14 context-handoff rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        for rule_name in CONTEXT_HANDOFF_RULES:
            assert rule_name in rule_names, f"Missing rule: {rule_name}"

    def test_all_rules_have_group(self, db, manager) -> None:
        """All context-handoff rules should have group='context-handoff'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in CONTEXT_HANDOFF_RULES:
                body = json.loads(row.definition_json)
                assert body.get("group") == "context-handoff", f"{row.name} missing group"

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in CONTEXT_HANDOFF_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                assert body.effect.type in {
                    "set_variable",
                    "inject_context",
                    "mcp_call",
                }


# ═══════════════════════════════════════════════════════════════════════
# clear-pending-context-reset-on-start
# ═══════════════════════════════════════════════════════════════════════


class TestClearPendingContextResetOnStart:
    """Clear pending_context_reset flag on session_start."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("clear-pending-context-reset-on-start")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "pending_context_reset"

    def test_has_when_condition(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("clear-pending-context-reset-on-start")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "pending_context_reset" in body.when


# ═══════════════════════════════════════════════════════════════════════
# capture-baseline-dirty-files-on-start
# ═══════════════════════════════════════════════════════════════════════


class TestCaptureBaselineDirtyFilesOnStart:
    """Capture baseline dirty files on session_start."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("capture-baseline-dirty-files-on-start")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "mcp_call"
        assert body.effect.server == "gobby-sessions"
        assert body.effect.tool == "capture_baseline_dirty_files"


# ═══════════════════════════════════════════════════════════════════════
# inject-previous-session-summary
# ═══════════════════════════════════════════════════════════════════════


class TestInjectPreviousSessionSummary:
    """Inject previous session summary on clear."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-previous-session-summary")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "inject_context"
        assert body.effect.template is not None
        assert "Previous Session Context" in body.effect.template

    def test_has_when_condition(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-previous-session-summary")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "clear" in body.when


# ═══════════════════════════════════════════════════════════════════════
# inject-compact-handoff
# ═══════════════════════════════════════════════════════════════════════


class TestInjectCompactHandoff:
    """Inject compact handoff context after compaction."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-compact-handoff")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "inject_context"
        assert body.effect.template is not None
        assert "Continuation Context" in body.effect.template

    def test_has_when_condition(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-compact-handoff")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "compact" in body.when


# ═══════════════════════════════════════════════════════════════════════
# task-sync-import-on-start
# ═══════════════════════════════════════════════════════════════════════


class TestTaskSyncImportOnStart:
    """Import tasks from JSONL on session_start."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-import-on-start")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "mcp_call"
        assert body.effect.server == "gobby-tasks"
        assert body.effect.tool == "sync_import"


# ═══════════════════════════════════════════════════════════════════════
# inject-skills-on-start
# ═══════════════════════════════════════════════════════════════════════


class TestInjectSkillsOnStart:
    """Inject skills guide on session_start (not resume)."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-skills-on-start")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "inject_context"
        assert body.effect.template is not None

    def test_has_when_condition(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-skills-on-start")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "resume" in body.when


# ═══════════════════════════════════════════════════════════════════════
# inject-task-context-on-start
# ═══════════════════════════════════════════════════════════════════════


class TestInjectTaskContextOnStart:
    """Inject active task context on session_start (not resume)."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-task-context-on-start")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "inject_context"
        assert body.effect.template is not None

    def test_has_when_condition(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-task-context-on-start")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "resume" in body.when


# ═══════════════════════════════════════════════════════════════════════
# inject-error-triage-policy
# ═══════════════════════════════════════════════════════════════════════


class TestInjectErrorTriagePolicy:
    """Inject pre-existing error triage policy on session_start."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-error-triage-policy")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "inject_context"
        assert body.effect.template is not None
        assert "Pre-Existing" in body.effect.template

    def test_has_when_condition(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("inject-error-triage-policy")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "resume" in body.when


# ═══════════════════════════════════════════════════════════════════════
# generate-handoff-on-end
# ═══════════════════════════════════════════════════════════════════════


class TestGenerateHandoffOnEnd:
    """Generate session handoff on session_end."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("generate-handoff-on-end")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_end"
        assert body.effect.type == "mcp_call"
        assert body.effect.server == "gobby-sessions"
        assert body.effect.tool == "generate_handoff"

    def test_has_arguments(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("generate-handoff-on-end")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.effect.arguments is not None
        assert body.effect.arguments.get("prompt") == "handoff/session_end"


# ═══════════════════════════════════════════════════════════════════════
# task-sync-export-on-end
# ═══════════════════════════════════════════════════════════════════════


class TestTaskSyncExportOnEnd:
    """Export tasks to JSONL on session_end."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-export-on-end")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_end"
        assert body.effect.type == "mcp_call"
        assert body.effect.server == "gobby-tasks"
        assert body.effect.tool == "sync_export"


# ═══════════════════════════════════════════════════════════════════════
# set-pending-context-reset-on-compact
# ═══════════════════════════════════════════════════════════════════════


class TestSetPendingContextResetOnCompact:
    """Set pending_context_reset flag before compaction."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("set-pending-context-reset-on-compact")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "pre_compact"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "pending_context_reset"

    def test_has_gemini_filter(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("set-pending-context-reset-on-compact")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "gemini" in body.when


# ═══════════════════════════════════════════════════════════════════════
# extract-handoff-context-on-compact
# ═══════════════════════════════════════════════════════════════════════


class TestExtractHandoffContextOnCompact:
    """Extract structured context before compaction."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("extract-handoff-context-on-compact")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "pre_compact"
        assert body.effect.type == "mcp_call"
        assert body.effect.server == "gobby-sessions"
        assert body.effect.tool == "extract_handoff_context"

    def test_has_gemini_filter(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("extract-handoff-context-on-compact")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "gemini" in body.when


# ═══════════════════════════════════════════════════════════════════════
# task-sync-export-on-compact
# ═══════════════════════════════════════════════════════════════════════


class TestTaskSyncExportOnCompact:
    """Export tasks to JSONL before compaction."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-export-on-compact")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "pre_compact"
        assert body.effect.type == "mcp_call"
        assert body.effect.server == "gobby-tasks"
        assert body.effect.tool == "sync_export"

    def test_has_gemini_filter(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-export-on-compact")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "gemini" in body.when


# ═══════════════════════════════════════════════════════════════════════
# generate-handoff-on-compact
# ═══════════════════════════════════════════════════════════════════════


class TestGenerateHandoffOnCompact:
    """Generate compact handoff summary before compaction."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("generate-handoff-on-compact")
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "pre_compact"
        assert body.effect.type == "mcp_call"
        assert body.effect.server == "gobby-sessions"
        assert body.effect.tool == "generate_handoff"

    def test_has_compact_mode_arg(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("generate-handoff-on-compact")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.effect.arguments is not None
        assert body.effect.arguments.get("mode") == "compact"

    def test_has_gemini_filter(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("generate-handoff-on-compact")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "gemini" in body.when
