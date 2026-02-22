"""Tests for messaging.yaml push delivery rules.

Covers 4 rules:
- deliver-pending-messages: calls MCP on before_agent
- activate-pending-command: activates on before_agent when has_pending_command
- command-tool-restriction: blocks disallowed tools when command active
- command-exit-condition: auto-completes on after_tool when exit condition met
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent
from gobby.workflows.rule_engine import RuleEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path) -> LocalDatabase:
    db_path = tmp_path / "test_messaging_rules.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def manager(db: LocalDatabase) -> LocalWorkflowDefinitionManager:
    return LocalWorkflowDefinitionManager(db)


def _make_event(
    event_type: HookEventType = HookEventType.BEFORE_TOOL,
    data: dict[str, Any] | None = None,
) -> HookEvent:
    return HookEvent(
        event_type=event_type,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data or {},
    )


def _insert_rule(
    manager: LocalWorkflowDefinitionManager,
    name: str,
    body: RuleDefinitionBody,
    priority: int = 100,
) -> str:
    row = manager.create(
        name=name,
        definition_json=body.model_dump_json(),
        workflow_type="rule",
        priority=priority,
        enabled=True,
    )
    return row.id


# ═══════════════════════════════════════════════════════════════════════
# deliver-pending-messages
# ═══════════════════════════════════════════════════════════════════════


class TestDeliverPendingMessages:
    """deliver-pending-messages calls MCP on before_agent."""

    @pytest.mark.asyncio
    async def test_fires_on_before_agent(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(
            manager,
            "deliver-pending-messages",
            RuleDefinitionBody(
                event=RuleEvent.BEFORE_AGENT,
                effect=RuleEffect(
                    type="mcp_call",
                    server="gobby-agents",
                    tool="deliver_pending_messages",
                ),
            ),
            priority=10,
        )

        engine = RuleEngine(db)
        event = _make_event(HookEventType.BEFORE_AGENT)
        response = await engine.evaluate(event, session_id="sess-1", variables={})

        assert response.decision == "allow"
        mcp_calls = response.metadata.get("mcp_calls", [])
        assert len(mcp_calls) == 1

    @pytest.mark.asyncio
    async def test_records_correct_mcp_call(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(
            manager,
            "deliver-pending-messages",
            RuleDefinitionBody(
                event=RuleEvent.BEFORE_AGENT,
                effect=RuleEffect(
                    type="mcp_call",
                    server="gobby-agents",
                    tool="deliver_pending_messages",
                ),
            ),
            priority=10,
        )

        engine = RuleEngine(db)
        event = _make_event(HookEventType.BEFORE_AGENT)
        response = await engine.evaluate(event, session_id="sess-1", variables={})

        call = response.metadata["mcp_calls"][0]
        assert call["server"] == "gobby-agents"
        assert call["tool"] == "deliver_pending_messages"


# ═══════════════════════════════════════════════════════════════════════
# activate-pending-command
# ═══════════════════════════════════════════════════════════════════════


class TestActivatePendingCommand:
    """activate-pending-command fires when has_pending_command is set."""

    @pytest.mark.asyncio
    async def test_fires_when_has_pending_command(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(
            manager,
            "activate-pending-command",
            RuleDefinitionBody(
                event=RuleEvent.BEFORE_AGENT,
                when="variables.get('has_pending_command')",
                effect=RuleEffect(
                    type="mcp_call",
                    server="gobby-agents",
                    tool="activate_command",
                ),
            ),
            priority=15,
        )

        engine = RuleEngine(db)
        event = _make_event(HookEventType.BEFORE_AGENT)
        variables: dict[str, Any] = {"has_pending_command": True}
        response = await engine.evaluate(event, session_id="sess-1", variables=variables)

        assert response.decision == "allow"
        mcp_calls = response.metadata.get("mcp_calls", [])
        assert len(mcp_calls) == 1
        assert mcp_calls[0]["tool"] == "activate_command"

    @pytest.mark.asyncio
    async def test_skips_when_no_pending_command(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(
            manager,
            "activate-pending-command",
            RuleDefinitionBody(
                event=RuleEvent.BEFORE_AGENT,
                when="variables.get('has_pending_command')",
                effect=RuleEffect(
                    type="mcp_call",
                    server="gobby-agents",
                    tool="activate_command",
                ),
            ),
            priority=15,
        )

        engine = RuleEngine(db)
        event = _make_event(HookEventType.BEFORE_AGENT)
        response = await engine.evaluate(event, session_id="sess-1", variables={})

        assert response.decision == "allow"
        mcp_calls = response.metadata.get("mcp_calls", [])
        assert len(mcp_calls) == 0


# ═══════════════════════════════════════════════════════════════════════
# command-tool-restriction
# ═══════════════════════════════════════════════════════════════════════


class TestCommandToolRestriction:
    """command-tool-restriction blocks disallowed tools when command active."""

    def _rule_body(self) -> RuleDefinitionBody:
        return RuleDefinitionBody(
            event=RuleEvent.BEFORE_TOOL,
            when=(
                "variables.get('command_id') "
                "and variables.get('allowed_tools') "
                "and event.data.get('tool_name') not in variables.get('allowed_tools', [])"
            ),
            effect=RuleEffect(
                type="block",
                reason="Tool not allowed by active command",
            ),
        )

    @pytest.mark.asyncio
    async def test_blocks_disallowed_tool(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(manager, "command-tool-restriction", self._rule_body(), priority=5)

        engine = RuleEngine(db)
        event = _make_event(HookEventType.BEFORE_TOOL, data={"tool_name": "Write"})
        variables: dict[str, Any] = {
            "command_id": "cmd-1",
            "allowed_tools": ["Read", "Grep"],
        }
        response = await engine.evaluate(event, session_id="sess-1", variables=variables)

        assert response.decision == "block"
        assert "not allowed" in (response.reason or "").lower()

    @pytest.mark.asyncio
    async def test_allows_permitted_tool(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(manager, "command-tool-restriction", self._rule_body(), priority=5)

        engine = RuleEngine(db)
        event = _make_event(HookEventType.BEFORE_TOOL, data={"tool_name": "Read"})
        variables: dict[str, Any] = {
            "command_id": "cmd-1",
            "allowed_tools": ["Read", "Grep"],
        }
        response = await engine.evaluate(event, session_id="sess-1", variables=variables)

        assert response.decision == "allow"

    @pytest.mark.asyncio
    async def test_no_restriction_without_command(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(manager, "command-tool-restriction", self._rule_body(), priority=5)

        engine = RuleEngine(db)
        event = _make_event(HookEventType.BEFORE_TOOL, data={"tool_name": "Write"})
        response = await engine.evaluate(event, session_id="sess-1", variables={})

        assert response.decision == "allow"


# ═══════════════════════════════════════════════════════════════════════
# command-exit-condition
# ═══════════════════════════════════════════════════════════════════════


class TestCommandExitCondition:
    """command-exit-condition auto-completes when exit condition met."""

    def _rule_body(self) -> RuleDefinitionBody:
        return RuleDefinitionBody(
            event=RuleEvent.AFTER_TOOL,
            when=(
                "variables.get('command_id') "
                "and variables.get('exit_condition_met')"
            ),
            effect=RuleEffect(
                type="mcp_call",
                server="gobby-agents",
                tool="complete_command",
            ),
        )

    @pytest.mark.asyncio
    async def test_fires_when_exit_condition_met(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(manager, "command-exit-condition", self._rule_body(), priority=90)

        engine = RuleEngine(db)
        event = _make_event(HookEventType.AFTER_TOOL)
        variables: dict[str, Any] = {
            "command_id": "cmd-1",
            "exit_condition_met": True,
        }
        response = await engine.evaluate(event, session_id="sess-1", variables=variables)

        assert response.decision == "allow"
        mcp_calls = response.metadata.get("mcp_calls", [])
        assert len(mcp_calls) == 1
        assert mcp_calls[0]["tool"] == "complete_command"

    @pytest.mark.asyncio
    async def test_skips_when_exit_not_met(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(manager, "command-exit-condition", self._rule_body(), priority=90)

        engine = RuleEngine(db)
        event = _make_event(HookEventType.AFTER_TOOL)
        variables: dict[str, Any] = {"command_id": "cmd-1"}
        response = await engine.evaluate(event, session_id="sess-1", variables=variables)

        assert response.decision == "allow"
        mcp_calls = response.metadata.get("mcp_calls", [])
        assert len(mcp_calls) == 0

    @pytest.mark.asyncio
    async def test_skips_without_command(
        self, db: LocalDatabase, manager: LocalWorkflowDefinitionManager
    ) -> None:
        _insert_rule(manager, "command-exit-condition", self._rule_body(), priority=90)

        engine = RuleEngine(db)
        event = _make_event(HookEventType.AFTER_TOOL)
        variables: dict[str, Any] = {"exit_condition_met": True}
        response = await engine.evaluate(event, session_id="sess-1", variables=variables)

        mcp_calls = response.metadata.get("mcp_calls", [])
        assert len(mcp_calls) == 0
