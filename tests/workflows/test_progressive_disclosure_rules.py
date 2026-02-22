"""Tests for progressive-disclosure.yaml rules.

Verifies blocking rules enforce progressive disclosure (list_mcp_servers →
list_tools → get_tool_schema → call_tool), tracker rules record state,
and reset rules clear state on context loss.
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
    db_path = tmp_path / "test_progressive_disclosure.db"
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


PROGRESSIVE_DISCLOSURE_RULES = {
    "require-servers-listed",
    "require-server-listed-for-schema",
    "require-schema-before-call",
    "track-schema-lookup",
    "track-servers-listed",
    "track-listed-servers",
    "reset-unlocked-tools",
    "reset-servers-listed",
    "reset-listed-servers",
}


class TestProgressiveDisclosureSync:
    """Test that progressive-disclosure.yaml syncs correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All progressive-disclosure rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        assert PROGRESSIVE_DISCLOSURE_RULES.issubset(rule_names), (
            f"Missing: {PROGRESSIVE_DISCLOSURE_RULES - rule_names}"
        )

    def test_all_rules_have_group(self, db, manager) -> None:
        """All rules should have group='progressive-disclosure'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in PROGRESSIVE_DISCLOSURE_RULES:
                body = json.loads(row.definition_json)
                assert body.get("group") == "progressive-disclosure", (
                    f"{row.name} missing group"
                )

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in PROGRESSIVE_DISCLOSURE_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                assert body.effect.type in {"block", "set_variable"}


class TestRequireServersListed:
    """Verify require-servers-listed blocks list_tools without list_mcp_servers."""

    def test_blocks_list_tools(self, db, manager) -> None:
        """Should block mcp__gobby__list_tools."""
        _sync_bundled(db)

        row = manager.get_by_name("require-servers-listed")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert "mcp__gobby__list_tools" in body.effect.tools

    def test_when_checks_servers_listed(self, db, manager) -> None:
        """Should check enforce_tool_schema_check and servers_listed."""
        _sync_bundled(db)

        row = manager.get_by_name("require-servers-listed")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "servers_listed" in body.when
        assert "enforce_tool_schema_check" in body.when


class TestRequireServerListedForSchema:
    """Verify require-server-listed-for-schema blocks get_tool_schema."""

    def test_blocks_get_tool_schema(self, db, manager) -> None:
        """Should block mcp__gobby__get_tool_schema."""
        _sync_bundled(db)

        row = manager.get_by_name("require-server-listed-for-schema")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert "mcp__gobby__get_tool_schema" in body.effect.tools

    def test_when_checks_is_server_listed(self, db, manager) -> None:
        """Should use is_server_listed helper."""
        _sync_bundled(db)

        row = manager.get_by_name("require-server-listed-for-schema")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "is_server_listed" in body.when


class TestRequireSchemaBeforeCall:
    """Verify require-schema-before-call blocks call_tool without schema."""

    def test_blocks_call_tool(self, db, manager) -> None:
        """Should block mcp__gobby__call_tool."""
        _sync_bundled(db)

        row = manager.get_by_name("require-schema-before-call")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        assert body.effect.type == "block"
        assert "mcp__gobby__call_tool" in body.effect.tools

    def test_when_checks_tool_unlocked(self, db, manager) -> None:
        """Should check is_tool_unlocked and is_discovery_tool."""
        _sync_bundled(db)

        row = manager.get_by_name("require-schema-before-call")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "is_tool_unlocked" in body.when
        assert "is_discovery_tool" in body.when


class TestTrackSchemaLookup:
    """Verify track-schema-lookup records schema lookups."""

    def test_is_set_variable_effect(self, db, manager) -> None:
        """Should use set_variable to track unlocked_tools."""
        _sync_bundled(db)

        row = manager.get_by_name("track-schema-lookup")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "unlocked_tools"

    def test_when_matches_get_tool_schema(self, db, manager) -> None:
        """Should fire on get_tool_schema calls."""
        _sync_bundled(db)

        row = manager.get_by_name("track-schema-lookup")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "get_tool_schema" in body.when


class TestTrackServersListed:
    """Verify track-servers-listed marks servers as listed."""

    def test_sets_servers_listed(self, db, manager) -> None:
        """Should set servers_listed to true."""
        _sync_bundled(db)

        row = manager.get_by_name("track-servers-listed")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "servers_listed"
        assert body.effect.value is True

    def test_when_matches_list_mcp_servers(self, db, manager) -> None:
        """Should fire on list_mcp_servers calls."""
        _sync_bundled(db)

        row = manager.get_by_name("track-servers-listed")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "list_mcp_servers" in body.when


class TestTrackListedServers:
    """Verify track-listed-servers records server names."""

    def test_sets_listed_servers(self, db, manager) -> None:
        """Should set listed_servers variable."""
        _sync_bundled(db)

        row = manager.get_by_name("track-listed-servers")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "listed_servers"

    def test_when_matches_list_tools(self, db, manager) -> None:
        """Should fire on list_tools calls."""
        _sync_bundled(db)

        row = manager.get_by_name("track-listed-servers")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "list_tools" in body.when


class TestResetRules:
    """Verify reset rules clear state on context loss."""

    def test_reset_unlocked_tools(self, db, manager) -> None:
        """Should reset unlocked_tools to empty list on session_start."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-unlocked-tools")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.type == "set_variable"
        assert body.effect.variable == "unlocked_tools"
        assert body.effect.value == []

    def test_reset_servers_listed(self, db, manager) -> None:
        """Should reset servers_listed to false on session_start."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-servers-listed")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.variable == "servers_listed"
        assert body.effect.value is False

    def test_reset_listed_servers(self, db, manager) -> None:
        """Should reset listed_servers to empty list on session_start."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-listed-servers")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"
        assert body.effect.variable == "listed_servers"
        assert body.effect.value == []

    def test_resets_fire_on_clear_compact_resume(self, db, manager) -> None:
        """Reset rules should fire on clear, compact, and conditional resume."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-unlocked-tools")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "clear" in body.when
        assert "compact" in body.when


class TestPriorityOrdering:
    """Verify priority ordering within progressive-disclosure group."""

    def test_blocks_ordered_before_trackers(self, db, manager) -> None:
        """Block rules should have lower or equal priority numbers to tracker rules."""
        _sync_bundled(db)

        block_rule = manager.get_by_name("require-servers-listed")
        tracker_rule = manager.get_by_name("track-schema-lookup")

        assert block_rule is not None
        assert tracker_rule is not None
        assert block_rule.priority <= tracker_rule.priority
