"""Tests for sync rules.

Verifies JSONL sync rules sync correctly and have proper structure.
These rules handle import/export of tasks and memories via .gobby/*.jsonl files.

Sync rules (all tagged with 'sync' for selective exclusion by agents):
- task-sync-import-on-start: mcp_call on session_start
- task-sync-export-on-end: mcp_call on session_end
- task-sync-export-on-compact: mcp_call on pre_compact
- memory-sync-import: mcp_call on session_start
- memory-sync-export-on-end: mcp_call on session_end
- memory-sync-export-on-compact: mcp_call on pre_compact
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

SYNC_RULES = {
    "task-sync-import-on-start",
    "task-sync-export-on-end",
    "task-sync-export-on-compact",
    "memory-sync-import",
    "memory-sync-export-on-end",
    "memory-sync-export-on-compact",
}


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_sync_rules.db"
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


class TestSyncRulesSync:
    """Test that sync rules sync correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All sync rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        for rule_name in SYNC_RULES:
            assert rule_name in rule_names, f"Missing rule: {rule_name}"

    def test_all_rules_have_sync_group(self, db, manager) -> None:
        """All sync rules should have group='sync'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in SYNC_RULES:
                body = json.loads(row.definition_json)
                assert body.get("group") == "sync", f"{row.name} missing group"

    def test_all_rules_have_sync_tag(self, db, manager) -> None:
        """All sync rules should have the 'sync' tag for selective exclusion."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in SYNC_RULES:
                assert row.tags is not None
                assert "sync" in row.tags, f"{row.name} missing 'sync' tag"

    def test_all_rules_are_mcp_call(self, db, manager) -> None:
        """All sync rules should be mcp_call effects."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in SYNC_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                assert body.effects[0].type == "mcp_call", f"{row.name} wrong effect type"


# ═══════════════════════════════════════════════════════════════════════
# task-sync-import-on-start
# ═══════════════════════════════════════════════════════════════════════


class TestTaskSyncImportOnStart:
    """Import tasks from JSONL on session_start."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-import-on-start", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effects[0].type == "mcp_call"
        assert body.effects[0].server == "gobby-tasks"
        assert body.effects[0].tool == "sync_import"


# ═══════════════════════════════════════════════════════════════════════
# task-sync-export-on-end
# ═══════════════════════════════════════════════════════════════════════


class TestTaskSyncExportOnEnd:
    """Export tasks to JSONL on session_end."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-export-on-end", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_end"
        assert body.effects[0].type == "mcp_call"
        assert body.effects[0].server == "gobby-tasks"
        assert body.effects[0].tool == "sync_export"


# ═══════════════════════════════════════════════════════════════════════
# task-sync-export-on-compact
# ═══════════════════════════════════════════════════════════════════════


class TestTaskSyncExportOnCompact:
    """Export tasks to JSONL before compaction."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-export-on-compact", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "pre_compact"
        assert body.effects[0].type == "mcp_call"
        assert body.effects[0].server == "gobby-tasks"
        assert body.effects[0].tool == "sync_export"

    def test_has_gemini_filter(self, db, manager) -> None:
        """Should filter out automatic gemini compactions."""
        _sync_bundled(db)
        row = manager.get_by_name("task-sync-export-on-compact", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "gemini" in body.when


# ═══════════════════════════════════════════════════════════════════════
# memory-sync-import
# ═══════════════════════════════════════════════════════════════════════


class TestMemorySyncImport:
    """Import memories from JSONL on session_start."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("memory-sync-import", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effects[0].type == "mcp_call"
        assert body.effects[0].server == "gobby-memory"
        assert body.effects[0].tool == "sync_import"


# ═══════════════════════════════════════════════════════════════════════
# memory-sync-export-on-end
# ═══════════════════════════════════════════════════════════════════════


class TestMemorySyncExportOnEnd:
    """Export memories to JSONL on session_end."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("memory-sync-export-on-end", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_end"
        assert body.effects[0].type == "mcp_call"
        assert body.effects[0].server == "gobby-memory"
        assert body.effects[0].tool == "sync_export"


# ═══════════════════════════════════════════════════════════════════════
# memory-sync-export-on-compact
# ═══════════════════════════════════════════════════════════════════════


class TestMemorySyncExportOnCompact:
    """Export memories to JSONL before compaction."""

    def test_event_and_effect(self, db, manager) -> None:
        _sync_bundled(db)
        row = manager.get_by_name("memory-sync-export-on-compact", include_templates=True)
        assert row is not None
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "pre_compact"
        assert body.effects[0].type == "mcp_call"
        assert body.effects[0].server == "gobby-memory"
        assert body.effects[0].tool == "sync_export"

    def test_has_gemini_filter(self, db, manager) -> None:
        """Should filter out automatic gemini compactions."""
        _sync_bundled(db)
        row = manager.get_by_name("memory-sync-export-on-compact", include_templates=True)
        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.when is not None
        assert "gemini" in body.when
