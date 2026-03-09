"""Tests for progressive-discovery rules.

Verifies auto-heal rules enforce progressive discovery
(list_mcp_servers -> list_tools -> get_tool_schema -> call_tool), tracker rules
record state, and reset rules clear state on context loss.

Includes integration tests that exercise the full RuleEngine.evaluate() flow
to verify conditions like is_server_listed actually resolve correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody
from gobby.workflows.rule_engine import RuleEngine
from gobby.workflows.sync import sync_bundled_rules

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_progressive_discovery.db"
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


PROGRESSIVE_DISCLOSURE_RULES = {
    "require-servers-listed",
    "require-server-listed-for-schema",
    "require-schema-before-call",
    "track-schema-lookup",
    "track-servers-listed",
    "track-listed-servers",
    "reset-progressive-discovery",
}


class TestProgressiveDisclosureSync:
    """Test that progressive-discovery rules sync correctly."""

    def test_bundled_file_syncs_all_rules(self, db, manager) -> None:
        """All progressive-discovery rules should sync to workflow_definitions."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        rule_names = {r.name for r in rules}

        assert PROGRESSIVE_DISCLOSURE_RULES.issubset(rule_names), (
            f"Missing: {PROGRESSIVE_DISCLOSURE_RULES - rule_names}"
        )

    def test_all_rules_have_progressive_discovery_tag(self, db, manager) -> None:
        """All rules should be tagged with 'progressive-discovery'."""
        _sync_bundled(db)

        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in PROGRESSIVE_DISCLOSURE_RULES:
                assert row.tags and "progressive-discovery" in row.tags, (
                    f"{row.name} missing 'progressive-discovery' tag"
                )

    def test_all_rules_are_valid_pydantic(self, db, manager) -> None:
        """All synced rules should be valid RuleDefinitionBody instances."""
        _sync_bundled(db)

        valid_types = {"block", "set_variable", "inject_context", "mcp_call"}
        rules = manager.list_all(workflow_type="rule")
        for row in rules:
            if row.name in PROGRESSIVE_DISCLOSURE_RULES:
                body = RuleDefinitionBody.model_validate_json(row.definition_json)
                for effect in body.resolved_effects:
                    assert effect.type in valid_types


class TestRequireServersListed:
    """Verify require-servers-listed auto-heals list_tools without list_mcp_servers."""

    def test_has_mcp_call_effect(self, db, manager) -> None:
        """Should have mcp_call effect to auto-call list_mcp_servers."""
        _sync_bundled(db)

        row = manager.get_by_name("require-servers-listed")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        effects = body.resolved_effects
        mcp_effects = [e for e in effects if e.type == "mcp_call"]
        assert len(mcp_effects) == 1
        assert mcp_effects[0].server == "_proxy"
        assert mcp_effects[0].tool == "list_mcp_servers"
        assert mcp_effects[0].inject_result is True
        assert mcp_effects[0].block_on_failure is True

    def test_when_checks_servers_listed(self, db, manager) -> None:
        """Should check enforce_tool_schema_check, servers_listed, and tool name."""
        _sync_bundled(db)

        row = manager.get_by_name("require-servers-listed")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "servers_listed" in body.when
        assert "enforce_tool_schema_check" in body.when
        assert "list_tools" in body.when


class TestRequireServerListedForSchema:
    """Verify require-server-listed-for-schema auto-heals get_tool_schema."""

    def test_has_auto_heal_effects(self, db, manager) -> None:
        """Should have mcp_call effects for list_mcp_servers and list_tools."""
        _sync_bundled(db)

        row = manager.get_by_name("require-server-listed-for-schema")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        effects = body.resolved_effects
        mcp_effects = [e for e in effects if e.type == "mcp_call"]
        assert len(mcp_effects) == 2
        assert mcp_effects[0].tool == "list_mcp_servers"
        assert mcp_effects[1].tool == "list_tools"
        assert mcp_effects[1].block_on_failure is True

    def test_when_checks_is_server_listed(self, db, manager) -> None:
        """Should use is_server_listed helper and check tool name."""
        _sync_bundled(db)

        row = manager.get_by_name("require-server-listed-for-schema")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "is_server_listed" in body.when
        assert "get_tool_schema" in body.when


class TestRequireSchemaBeforeCall:
    """Verify require-schema-before-call auto-heals call_tool without schema."""

    def test_has_full_chain_effects(self, db, manager) -> None:
        """Should have mcp_call effects for full discovery chain."""
        _sync_bundled(db)

        row = manager.get_by_name("require-schema-before-call")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "before_tool"
        effects = body.resolved_effects
        mcp_effects = [e for e in effects if e.type == "mcp_call"]
        assert len(mcp_effects) == 3
        assert mcp_effects[0].tool == "list_mcp_servers"
        assert mcp_effects[1].tool == "list_tools"
        assert mcp_effects[2].tool == "get_tool_schema"
        # list_tools blocks on failure; get_tool_schema injects error as context
        assert mcp_effects[1].block_on_failure is True
        assert mcp_effects[2].block_on_failure is False

    def test_when_checks_tool_unlocked(self, db, manager) -> None:
        """Should check is_tool_unlocked, is_discovery_tool, and call_tool."""
        _sync_bundled(db)

        row = manager.get_by_name("require-schema-before-call")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "is_tool_unlocked" in body.when
        assert "is_discovery_tool" in body.when
        assert "call_tool" in body.when


class TestTrackSchemaLookup:
    """Verify track-schema-lookup records schema lookups."""

    def test_is_set_variable_effect(self, db, manager) -> None:
        """Should use set_variable to track unlocked_tools."""
        _sync_bundled(db)

        row = manager.get_by_name("track-schema-lookup")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "after_tool"
        assert body.effects[0].type == "set_variable"
        assert body.effects[0].variable == "unlocked_tools"

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
        assert body.effects[0].type == "set_variable"
        assert body.effects[0].variable == "servers_listed"
        assert body.effects[0].value is True

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
        assert body.effects[0].type == "set_variable"
        assert body.effects[0].variable == "listed_servers"

    def test_when_matches_list_tools(self, db, manager) -> None:
        """Should fire on list_tools calls."""
        _sync_bundled(db)

        row = manager.get_by_name("track-listed-servers")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "list_tools" in body.when


class TestResetRules:
    """Verify reset-progressive-discovery multi-effect rule clears all state on context loss."""

    def test_resets_all_three_variables(self, db, manager) -> None:
        """Should reset unlocked_tools, servers_listed, and listed_servers."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-progressive-discovery")
        assert row is not None

        body = RuleDefinitionBody.model_validate_json(row.definition_json)
        assert body.event.value == "session_start"

        effects = body.resolved_effects
        assert len(effects) == 3

        vars_and_values = {e.variable: e.value for e in effects}
        assert vars_and_values["unlocked_tools"] == []
        assert vars_and_values["servers_listed"] is False
        assert vars_and_values["listed_servers"] == []

    def test_resets_fire_on_clear_compact_resume(self, db, manager) -> None:
        """Reset rule should fire on clear, compact, and conditional resume."""
        _sync_bundled(db)

        row = manager.get_by_name("reset-progressive-discovery")
        body = RuleDefinitionBody.model_validate_json(row.definition_json)

        assert body.when is not None
        assert "clear" in body.when
        assert "compact" in body.when


class TestPreseedRemoved:
    """Verify preseed-progressive-discovery has been removed."""

    def test_preseed_rule_does_not_exist(self, db, manager) -> None:
        """Preseed rule should not exist in workflow_definitions."""
        _sync_bundled(db)

        row = manager.get_by_name("preseed-progressive-discovery")
        assert row is None


class TestRuleDefinitionBodyToolsField:
    """Verify tools field on RuleDefinitionBody works as pre-filter."""

    def test_tools_field_accepted(self) -> None:
        """RuleDefinitionBody should accept a tools field."""
        from gobby.workflows.definitions import RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.BEFORE_TOOL,
            tools=["mcp__gobby__list_tools"],
            effect=RuleEffect(type="block", reason="test"),
        )
        assert body.tools == ["mcp__gobby__list_tools"]

    def test_tools_field_none_by_default(self) -> None:
        """RuleDefinitionBody.tools should default to None."""
        from gobby.workflows.definitions import RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.BEFORE_TOOL,
            effect=RuleEffect(type="block", reason="test"),
        )
        assert body.tools is None

    def test_auto_heal_rules_have_mcp_call_effects(self, db, manager) -> None:
        """Auto-heal rules should have mcp_call effects targeting _proxy."""
        _sync_bundled(db)

        for rule_name, expected_tool in [
            ("require-servers-listed", "list_mcp_servers"),
            ("require-server-listed-for-schema", "list_tools"),
            ("require-schema-before-call", "get_tool_schema"),
        ]:
            row = manager.get_by_name(rule_name)
            assert row is not None, f"{rule_name} not found"
            body = RuleDefinitionBody.model_validate_json(row.definition_json)
            mcp_effects = [e for e in body.resolved_effects if e.type == "mcp_call"]
            tools = [e.tool for e in mcp_effects]
            assert expected_tool in tools, f"{rule_name} missing mcp_call for {expected_tool}"


class TestPriorityOrdering:
    """Verify priority ordering within progressive-discovery group."""

    def test_blocks_ordered_before_trackers(self, db, manager) -> None:
        """Auto-heal rules should have lower or equal priority numbers to tracker rules."""
        _sync_bundled(db)

        block_rule = manager.get_by_name("require-servers-listed")
        tracker_rule = manager.get_by_name("track-schema-lookup")

        assert block_rule is not None
        assert tracker_rule is not None
        assert block_rule.priority <= tracker_rule.priority


def _make_hook_event(
    event_type: HookEventType,
    tool_name: str = "",
    tool_input: dict | None = None,
) -> HookEvent:
    """Create a HookEvent for testing."""
    data = {"tool_name": tool_name}
    if tool_input is not None:
        data["tool_input"] = tool_input
    return HookEvent(
        event_type=event_type,
        session_id="test-session-ext",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data,
        metadata={"_platform_session_id": "test-session"},
    )


class TestRuleEngineIntegration:
    """End-to-end tests: RuleEngine.evaluate() with progressive discovery rules.

    These test the actual condition evaluation path including is_server_listed,
    is_tool_unlocked, and is_discovery_tool. The auto-heal rules fire mcp_call
    effects (returned in metadata) instead of blocking.
    """

    @pytest.fixture
    def engine(self, db) -> RuleEngine:
        _sync_bundled(db)
        # Disable all rules first, then enable only the progressive discovery rules
        # (avoids interference from other rules that may have been synced as enabled)
        db.execute("UPDATE workflow_definitions SET enabled = 0")
        for name in PROGRESSIVE_DISCLOSURE_RULES:
            db.execute(
                "UPDATE workflow_definitions SET enabled = 1 WHERE name = ?",
                (name,),
            )
        return RuleEngine(db)

    @pytest.mark.asyncio
    async def test_get_tool_schema_auto_heals_when_server_not_listed(self, engine) -> None:
        """get_tool_schema should trigger auto-heal mcp_calls when server not listed."""
        variables = {"enforce_tool_schema_check": True, "listed_servers": []}
        event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        result = await engine.evaluate(event, "test-session", variables)
        # Auto-heal: allows with mcp_calls in metadata
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) > 0
        mcp_tools = [c["tool"] for c in mcp_calls]
        assert "list_mcp_servers" in mcp_tools
        assert "list_tools" in mcp_tools

    @pytest.mark.asyncio
    async def test_get_tool_schema_allowed_after_list_tools(self, engine) -> None:
        """get_tool_schema should be allowed after list_tools was called for that server."""
        variables = {
            "enforce_tool_schema_check": True,
            "listed_servers": ["gobby-tasks"],
        }
        event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "allow"
        # No auto-heal needed — no mcp_calls
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) == 0

    @pytest.mark.asyncio
    async def test_call_tool_auto_heals_when_schema_missing(self, engine) -> None:
        """call_tool should trigger auto-heal with full chain when schema not looked up."""
        variables = {
            "enforce_tool_schema_check": True,
            "unlocked_tools": [],
        }
        event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "test"},
            },
        )
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        mcp_tools = [c["tool"] for c in mcp_calls]
        assert "list_mcp_servers" in mcp_tools
        assert "get_tool_schema" in mcp_tools

    @pytest.mark.asyncio
    async def test_call_tool_allowed_after_schema_lookup(self, engine) -> None:
        """call_tool should be allowed after get_tool_schema was called."""
        variables = {
            "enforce_tool_schema_check": True,
            "unlocked_tools": ["gobby-tasks:create_task"],
        }
        event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "test"},
            },
        )
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_call_tool_allowed_for_discovery_tools(self, engine) -> None:
        """call_tool should allow discovery tools (list_tools, etc.) without schema."""
        variables = {
            "enforce_tool_schema_check": True,
            "unlocked_tools": [],
        }
        event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "list_tools",
                "arguments": {"server_name": "gobby-tasks"},
            },
        )
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_auto_heal_renders_jinja_in_arguments(self, engine) -> None:
        """Auto-heal mcp_call arguments should render Jinja templates from tool_input."""
        variables = {"enforce_tool_schema_check": True, "listed_servers": []}
        event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        result = await engine.evaluate(event, "test-session", variables)
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        list_tools_calls = [c for c in mcp_calls if c["tool"] == "list_tools"]
        assert len(list_tools_calls) == 1
        assert list_tools_calls[0]["arguments"]["server_name"] == "gobby-tasks"

    @pytest.mark.asyncio
    async def test_full_auto_heal_flow(self, engine) -> None:
        """Full flow: auto-heal fires mcp_calls, tracking rules still work."""
        variables: dict = {
            "enforce_tool_schema_check": True,
            "listed_servers": [],
            "unlocked_tools": [],
        }

        # Step 1: get_tool_schema triggers auto-heal (server not listed)
        event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) > 0
        # Auto-heal set_variable effects also fire, updating tracking
        assert variables.get("servers_listed") is True
        assert "gobby-tasks" in variables.get("listed_servers", [])

        # Step 2: After tracking is set, get_tool_schema doesn't trigger auto-heal
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) == 0

        # Step 3: call_tool triggers auto-heal (schema not looked up)
        call_event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "test"},
            },
        )
        result = await engine.evaluate(call_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        # Should include get_tool_schema but not list_tools (already listed)
        mcp_tools = [c["tool"] for c in mcp_calls]
        assert "get_tool_schema" in mcp_tools
        # set_variable effect updates tracking
        assert "gobby-tasks:create_task" in variables.get("unlocked_tools", [])

        # Step 4: call_tool now passes without auto-heal
        result = await engine.evaluate(call_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) == 0

    @pytest.mark.asyncio
    async def test_tracking_rules_set_variables_via_after_tool(self, engine) -> None:
        """Tracking rules should set variables when after_tool events fire.

        Regression test: previously, the tracking rules had truncated `when`
        conditions that only checked `event.data.mcp_tool` (set by CLI adapters)
        but not `event.data.tool_name` (set by the web chat SDK bridge). This
        meant tracking never fired for web chat sessions.
        """
        variables: dict = {
            "enforce_tool_schema_check": True,
        }

        # Step 1: Fire after_tool for list_mcp_servers (native tool name)
        after_list_servers = _make_hook_event(
            HookEventType.AFTER_TOOL,
            tool_name="mcp__gobby__list_mcp_servers",
        )
        result = await engine.evaluate(after_list_servers, "test-session", variables)
        assert result.decision == "allow"
        assert variables.get("servers_listed") is True, (
            "track-servers-listed should set servers_listed=True"
        )

        # Step 2: Fire after_tool for list_tools (native tool name)
        after_list_tools = _make_hook_event(
            HookEventType.AFTER_TOOL,
            tool_name="mcp__gobby__list_tools",
            tool_input={"server_name": "gobby-tasks"},
        )
        result = await engine.evaluate(after_list_tools, "test-session", variables)
        assert result.decision == "allow"
        assert "gobby-tasks" in variables.get("listed_servers", []), (
            "track-listed-servers should append server to listed_servers"
        )

        # Step 3: Fire after_tool for get_tool_schema (native tool name)
        after_schema = _make_hook_event(
            HookEventType.AFTER_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        result = await engine.evaluate(after_schema, "test-session", variables)
        assert result.decision == "allow"
        assert "gobby-tasks:create_task" in variables.get("unlocked_tools", []), (
            "track-schema-lookup should append server:tool to unlocked_tools"
        )

    @pytest.mark.asyncio
    async def test_full_round_trip_via_rule_engine(self, engine) -> None:
        """Full round-trip: auto-heal fires on before_tool, tracking still works via after_tool.

        This is the end-to-end test that proves the YAML rules work. Auto-heal
        rules fire mcp_call effects instead of blocking, and tracking rules
        still update variables on after_tool events.
        """
        variables: dict = {
            "enforce_tool_schema_check": True,
        }

        # get_tool_schema triggers auto-heal (not yet tracked)
        schema_event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        result = await engine.evaluate(schema_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) > 0  # Auto-heal fired

        # Simulate list_tools completing (after_tool fires tracking rule)
        after_list_tools = _make_hook_event(
            HookEventType.AFTER_TOOL,
            tool_name="mcp__gobby__list_tools",
            tool_input={"server_name": "gobby-tasks"},
        )
        await engine.evaluate(after_list_tools, "test-session", variables)

        # Now get_tool_schema passes without auto-heal (server listed)
        result = await engine.evaluate(schema_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) == 0

        # call_tool triggers auto-heal (schema not looked up yet)
        call_event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__call_tool",
            tool_input={
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "test"},
            },
        )
        result = await engine.evaluate(call_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert any(c["tool"] == "get_tool_schema" for c in mcp_calls)

        # Simulate get_tool_schema completing (after_tool fires tracking rule)
        after_schema = _make_hook_event(
            HookEventType.AFTER_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        await engine.evaluate(after_schema, "test-session", variables)

        # call_tool allowed without auto-heal (schema was looked up)
        result = await engine.evaluate(call_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        assert len(mcp_calls) == 0

    @pytest.mark.asyncio
    async def test_internal_server_auto_heals_without_list_tools(self, engine) -> None:
        """Without tracking, internal servers trigger auto-heal like any other server."""
        variables: dict = {
            "enforce_tool_schema_check": True,
            "listed_servers": [],
            "unlocked_tools": [],
        }

        # get_tool_schema for an internal server triggers auto-heal
        schema_event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "gobby-tasks", "tool_name": "create_task"},
        )
        result = await engine.evaluate(schema_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        list_tools_calls = [c for c in mcp_calls if c["tool"] == "list_tools"]
        assert len(list_tools_calls) == 1
        assert list_tools_calls[0]["arguments"]["server_name"] == "gobby-tasks"

        # get_tool_schema for an external server also triggers auto-heal
        ext_event = _make_hook_event(
            HookEventType.BEFORE_TOOL,
            tool_name="mcp__gobby__get_tool_schema",
            tool_input={"server_name": "context7", "tool_name": "get-library-docs"},
        )
        result = await engine.evaluate(ext_event, "test-session", variables)
        assert result.decision == "allow"
        mcp_calls = (result.metadata or {}).get("mcp_calls", [])
        list_tools_calls = [c for c in mcp_calls if c["tool"] == "list_tools"]
        assert len(list_tools_calls) == 1
        assert list_tools_calls[0]["arguments"]["server_name"] == "context7"
