"""Tests for dual evaluation: RuleEngine + legacy lifecycle in WorkflowHookHandler."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource
from gobby.workflows.hooks import WorkflowHookHandler

pytestmark = pytest.mark.unit


def _make_event(
    event_type: HookEventType = HookEventType.BEFORE_TOOL,
    session_id: str = "sess-123",
    data: dict | None = None,
) -> HookEvent:
    """Create a HookEvent for testing."""
    return HookEvent(
        event_type=event_type,
        session_id=session_id,
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data or {"tool_name": "Bash", "command": "ls"},
        metadata={"_platform_session_id": session_id},
    )


def _make_handler(
    legacy_response: HookResponse | None = None,
    rule_response: HookResponse | None = None,
) -> WorkflowHookHandler:
    """Create a WorkflowHookHandler with mocked engine and rule_engine."""
    engine = MagicMock()
    engine.evaluate_all_lifecycle_workflows = AsyncMock(
        return_value=legacy_response or HookResponse(decision="allow"),
    )

    rule_engine = MagicMock()
    rule_engine.evaluate = AsyncMock(
        return_value=rule_response or HookResponse(decision="allow"),
    )

    return WorkflowHookHandler(engine=engine, rule_engine=rule_engine)


class TestDualEvaluationOrder:
    """Verify RuleEngine runs first, then legacy."""

    def test_rule_engine_called_before_legacy(self) -> None:
        """RuleEngine.evaluate() should be called before legacy evaluation."""
        call_order: list[str] = []

        engine = MagicMock()

        async def mock_legacy(event):
            call_order.append("legacy")
            return HookResponse(decision="allow")

        engine.evaluate_all_lifecycle_workflows = mock_legacy

        rule_engine = MagicMock()

        async def mock_rules(event, session_id, variables, eval_context=None):
            call_order.append("rules")
            return HookResponse(decision="allow")

        rule_engine.evaluate = mock_rules

        handler = WorkflowHookHandler(engine=engine, rule_engine=rule_engine)
        handler.evaluate(_make_event())

        assert call_order == ["rules", "legacy"]

    def test_both_engines_called_on_allow(self) -> None:
        """When rules allow, legacy should also be called."""
        handler = _make_handler(
            rule_response=HookResponse(decision="allow"),
            legacy_response=HookResponse(decision="allow"),
        )
        event = _make_event()
        handler.evaluate(event)

        handler.engine.evaluate_all_lifecycle_workflows.assert_called_once_with(event)


class TestRuleBlockShortCircuits:
    """Block from rules should skip legacy evaluation."""

    def test_rule_block_skips_legacy(self) -> None:
        """If rules return block, legacy should not be called."""
        handler = _make_handler(
            rule_response=HookResponse(decision="block", reason="Blocked by rule"),
        )
        result = handler.evaluate(_make_event())

        assert result.decision == "block"
        assert result.reason == "Blocked by rule"
        handler.engine.evaluate_all_lifecycle_workflows.assert_not_called()

    def test_rule_deny_skips_legacy(self) -> None:
        """If rules return deny, legacy should not be called."""
        handler = _make_handler(
            rule_response=HookResponse(decision="deny", reason="Denied by rule"),
        )
        result = handler.evaluate(_make_event())

        assert result.decision == "deny"
        handler.engine.evaluate_all_lifecycle_workflows.assert_not_called()


class TestContextMerging:
    """Context from both engines should be merged."""

    def test_rule_context_merged_with_legacy_context(self) -> None:
        """Context from both engines should be joined with double newline."""
        handler = _make_handler(
            rule_response=HookResponse(decision="allow", context="Rule context here"),
            legacy_response=HookResponse(decision="allow", context="Legacy context here"),
        )
        result = handler.evaluate(_make_event())

        assert result.decision == "allow"
        assert "Rule context here" in result.context
        assert "Legacy context here" in result.context

    def test_only_rule_context(self) -> None:
        """When only rules inject context, it should pass through."""
        handler = _make_handler(
            rule_response=HookResponse(decision="allow", context="Only rules"),
            legacy_response=HookResponse(decision="allow"),
        )
        result = handler.evaluate(_make_event())

        assert result.context == "Only rules"

    def test_only_legacy_context(self) -> None:
        """When only legacy injects context, it should pass through."""
        handler = _make_handler(
            rule_response=HookResponse(decision="allow"),
            legacy_response=HookResponse(decision="allow", context="Only legacy"),
        )
        result = handler.evaluate(_make_event())

        assert result.context == "Only legacy"

    def test_no_context_from_either(self) -> None:
        """When neither engine injects context, result context should be None."""
        handler = _make_handler()
        result = handler.evaluate(_make_event())

        assert result.context is None

    def test_rule_mcp_calls_preserved_in_metadata(self) -> None:
        """MCP calls from rules should be preserved in the merged response."""
        handler = _make_handler(
            rule_response=HookResponse(
                decision="allow",
                metadata={"mcp_calls": [{"server": "s", "tool": "t"}]},
            ),
            legacy_response=HookResponse(
                decision="allow",
                metadata={"discovered_workflows": [{"name": "w1"}]},
            ),
        )
        result = handler.evaluate(_make_event())

        assert "mcp_calls" in result.metadata
        assert result.metadata["mcp_calls"] == [{"server": "s", "tool": "t"}]


class TestDecisionMerging:
    """Decision merging between engines."""

    def test_legacy_block_wins_when_rules_allow(self) -> None:
        """If rules allow but legacy blocks, the block should be returned."""
        handler = _make_handler(
            rule_response=HookResponse(decision="allow"),
            legacy_response=HookResponse(decision="block", reason="Legacy blocks"),
        )
        result = handler.evaluate(_make_event())

        assert result.decision == "block"
        assert result.reason == "Legacy blocks"

    def test_legacy_system_message_preserved(self) -> None:
        """System message from legacy should be preserved in merged response."""
        handler = _make_handler(
            rule_response=HookResponse(decision="allow"),
            legacy_response=HookResponse(
                decision="allow",
                system_message="Handoff notification",
            ),
        )
        result = handler.evaluate(_make_event())

        assert result.system_message == "Handoff notification"


class TestDisagreementLogging:
    """Disagreement between engines should be logged."""

    def test_legacy_blocks_but_rules_allow_logs_warning(self, caplog) -> None:
        """When legacy blocks but rules allowed, a warning should be logged."""
        handler = _make_handler(
            rule_response=HookResponse(decision="allow"),
            legacy_response=HookResponse(decision="block", reason="Legacy says no"),
        )
        with caplog.at_level(logging.WARNING, logger="gobby.workflows.hooks"):
            handler.evaluate(_make_event())

        assert any("disagreement" in record.message.lower() for record in caplog.records)


class TestNoRuleEngine:
    """Handler should work without a rule engine (backward compatibility)."""

    def test_no_rule_engine_falls_back_to_legacy_only(self) -> None:
        """When rule_engine is None, only legacy evaluation should run."""
        engine = MagicMock()
        engine.evaluate_all_lifecycle_workflows = AsyncMock(
            return_value=HookResponse(decision="allow", context="Legacy only"),
        )

        handler = WorkflowHookHandler(engine=engine, rule_engine=None)
        result = handler.evaluate(_make_event())

        assert result.decision == "allow"
        assert result.context == "Legacy only"

    def test_disabled_handler_skips_everything(self) -> None:
        """Disabled handler returns allow without calling anything."""
        handler = _make_handler()
        handler._enabled = False
        result = handler.evaluate(_make_event())

        assert result.decision == "allow"
        handler.engine.evaluate_all_lifecycle_workflows.assert_not_called()
