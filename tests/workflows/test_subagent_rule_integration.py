"""Integration tests for is_subagent variable and rule engine interaction.

Verifies that:
- block-native-task-tools fires when is_subagent is False (default)
- block-native-task-tools is skipped when is_subagent is True
- reset-subagent-flag clears is_subagent on before_agent events
- Bidirectional toggle works within same session
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.workflows.rule_engine import RuleEngine
from gobby.workflows.sync import get_bundled_rules_path, sync_bundled_rules

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_subagent_rules.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def engine(db: LocalDatabase) -> RuleEngine:
    """Sync bundled rules and enable only the ones we're testing."""
    sync_bundled_rules(db, get_bundled_rules_path())
    db.execute("UPDATE workflow_definitions SET source = 'installed' WHERE source = 'template'")
    # Disable everything, then enable only our target rules
    db.execute("UPDATE workflow_definitions SET enabled = 0")
    for name in ("block-native-task-tools", "reset-subagent-flag"):
        db.execute(
            "UPDATE workflow_definitions SET enabled = 1 WHERE name = ?",
            (name,),
        )
    return RuleEngine(db)


def _make_hook_event(
    event_type: HookEventType,
    tool_name: str = "",
) -> HookEvent:
    return HookEvent(
        event_type=event_type,
        session_id="test-session-ext",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data={"tool_name": tool_name},
        metadata={"_platform_session_id": "test-session"},
    )


class TestSubagentRuleIntegration:
    """End-to-end: RuleEngine.evaluate() with is_subagent variable."""

    @pytest.mark.asyncio
    async def test_blocks_native_tools_when_not_subagent(self, engine) -> None:
        """TaskCreate should be blocked when is_subagent is False (default)."""
        variables: dict = {"is_subagent": False}
        event = _make_hook_event(HookEventType.BEFORE_TOOL, tool_name="TaskCreate")
        result = await engine.evaluate(event, "test-session", variables)

        assert result.decision == "block"
        assert "gobby-tasks" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_blocks_native_tools_when_variable_unset(self, engine) -> None:
        """TaskCreate should be blocked when is_subagent is not in variables at all."""
        variables: dict = {}
        event = _make_hook_event(HookEventType.BEFORE_TOOL, tool_name="TaskCreate")
        result = await engine.evaluate(event, "test-session", variables)

        assert result.decision == "block"

    @pytest.mark.asyncio
    async def test_allows_native_tools_when_subagent(self, engine) -> None:
        """TaskCreate should be allowed when is_subagent is True."""
        variables: dict = {"is_subagent": True}
        event = _make_hook_event(HookEventType.BEFORE_TOOL, tool_name="TaskCreate")
        result = await engine.evaluate(event, "test-session", variables)

        assert result.decision == "allow"

    @pytest.mark.asyncio
    async def test_allows_all_blocked_tools_when_subagent(self, engine) -> None:
        """All five blocked tools should be allowed when is_subagent is True."""
        variables: dict = {"is_subagent": True}
        for tool in ("TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TodoWrite"):
            event = _make_hook_event(HookEventType.BEFORE_TOOL, tool_name=tool)
            result = await engine.evaluate(event, "test-session", variables)
            assert result.decision == "allow", f"{tool} should be allowed for subagent"

    @pytest.mark.asyncio
    async def test_bidirectional_toggle(self, engine) -> None:
        """Toggling is_subagent should change blocking behavior."""
        variables: dict = {"is_subagent": False}
        event = _make_hook_event(HookEventType.BEFORE_TOOL, tool_name="TaskCreate")

        # Blocked when False
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "block"

        # Allowed when True
        variables["is_subagent"] = True
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "allow"

        # Blocked again when False
        variables["is_subagent"] = False
        result = await engine.evaluate(event, "test-session", variables)
        assert result.decision == "block"

    @pytest.mark.asyncio
    async def test_reset_rule_clears_is_subagent_on_before_agent(self, engine) -> None:
        """reset-subagent-flag should set is_subagent=False on before_agent."""
        variables: dict = {"is_subagent": True}
        event = _make_hook_event(HookEventType.BEFORE_AGENT)
        result = await engine.evaluate(event, "test-session", variables)

        assert result.decision == "allow"
        # The set_variable effect should have mutated variables in-place
        assert variables["is_subagent"] is False

    @pytest.mark.asyncio
    async def test_reset_rule_noop_when_already_false(self, engine) -> None:
        """reset-subagent-flag should not fire when is_subagent is already False."""
        variables: dict = {"is_subagent": False}
        event = _make_hook_event(HookEventType.BEFORE_AGENT)
        result = await engine.evaluate(event, "test-session", variables)

        assert result.decision == "allow"
        assert variables["is_subagent"] is False
