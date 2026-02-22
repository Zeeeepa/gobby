"""Tests for RuleEvent, RuleEffect, and RuleDefinitionBody models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# --- RuleEvent tests ---


class TestRuleEvent:
    def test_enum_has_seven_values(self) -> None:
        from gobby.workflows.definitions import RuleEvent

        assert len(RuleEvent) == 7

    def test_enum_values(self) -> None:
        from gobby.workflows.definitions import RuleEvent

        assert RuleEvent.BEFORE_TOOL == "before_tool"
        assert RuleEvent.AFTER_TOOL == "after_tool"
        assert RuleEvent.BEFORE_AGENT == "before_agent"
        assert RuleEvent.SESSION_START == "session_start"
        assert RuleEvent.SESSION_END == "session_end"
        assert RuleEvent.STOP == "stop"
        assert RuleEvent.PRE_COMPACT == "pre_compact"

    def test_enum_is_str(self) -> None:
        """RuleEvent should be a str enum for JSON serialization."""
        from gobby.workflows.definitions import RuleEvent

        assert isinstance(RuleEvent.BEFORE_TOOL, str)
        assert RuleEvent.BEFORE_TOOL == "before_tool"

    def test_enum_from_string(self) -> None:
        from gobby.workflows.definitions import RuleEvent

        assert RuleEvent("before_tool") == RuleEvent.BEFORE_TOOL
        assert RuleEvent("stop") == RuleEvent.STOP

    def test_enum_invalid_value(self) -> None:
        from gobby.workflows.definitions import RuleEvent

        with pytest.raises(ValueError):
            RuleEvent("invalid_event")


# --- RuleEffect tests ---


class TestRuleEffect:
    def test_block_effect(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="block",
            reason="Claim a task first",
            tools=["Edit", "Write"],
        )
        assert effect.type == "block"
        assert effect.reason == "Claim a task first"
        assert effect.tools == ["Edit", "Write"]

    def test_block_effect_with_mcp_tools(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="block",
            reason="Commit first",
            mcp_tools=["gobby-tasks:close_task"],
        )
        assert effect.mcp_tools == ["gobby-tasks:close_task"]

    def test_block_effect_with_command_patterns(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="block",
            reason="Use uv run instead",
            tools=["Bash"],
            command_pattern=r"(?:^|[;&|])\s*python\b",
            command_not_pattern=r"uv\s+run",
        )
        assert effect.command_pattern == r"(?:^|[;&|])\s*python\b"
        assert effect.command_not_pattern == r"uv\s+run"

    def test_set_variable_effect(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="set_variable",
            variable="task_claimed",
            value=True,
        )
        assert effect.type == "set_variable"
        assert effect.variable == "task_claimed"
        assert effect.value is True

    def test_set_variable_with_expression(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="set_variable",
            variable="stop_attempts",
            value="variables.get('stop_attempts', 0) + 1",
        )
        assert effect.variable == "stop_attempts"
        assert effect.value == "variables.get('stop_attempts', 0) + 1"

    def test_inject_context_effect(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="inject_context",
            template="## Task Context\nYou are working on {{ task_ref }}.",
        )
        assert effect.type == "inject_context"
        assert "{{ task_ref }}" in effect.template

    def test_mcp_call_effect(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="mcp_call",
            server="gobby-memory",
            tool="recall_with_synthesis",
            arguments={"limit": 5},
        )
        assert effect.type == "mcp_call"
        assert effect.server == "gobby-memory"
        assert effect.tool == "recall_with_synthesis"
        assert effect.arguments == {"limit": 5}

    def test_mcp_call_background(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="mcp_call",
            server="gobby-memory",
            tool="background_digest_and_synthesize",
            arguments={"limit": 20},
            background=True,
        )
        assert effect.background is True

    def test_mcp_call_background_defaults_false(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(
            type="mcp_call",
            server="gobby-memory",
            tool="sync_import",
        )
        assert effect.background is False

    def test_invalid_type_rejected(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        with pytest.raises(ValidationError):
            RuleEffect(type="invalid_type")

    def test_four_valid_types(self) -> None:
        """All four effect types should be accepted."""
        from gobby.workflows.definitions import RuleEffect

        for effect_type in ("block", "set_variable", "inject_context", "mcp_call"):
            effect = RuleEffect(type=effect_type)
            assert effect.type == effect_type

    def test_defaults_are_none(self) -> None:
        from gobby.workflows.definitions import RuleEffect

        effect = RuleEffect(type="block")
        assert effect.reason is None
        assert effect.tools is None
        assert effect.mcp_tools is None
        assert effect.command_pattern is None
        assert effect.command_not_pattern is None
        assert effect.variable is None
        assert effect.value is None
        assert effect.template is None
        assert effect.server is None
        assert effect.tool is None
        assert effect.arguments is None
        assert effect.background is False


# --- RuleDefinitionBody tests ---


class TestRuleDefinitionBody:
    def test_minimal_block_rule(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.BEFORE_TOOL,
            effect=RuleEffect(type="block", reason="Not allowed", tools=["Edit"]),
        )
        assert body.event == RuleEvent.BEFORE_TOOL
        assert body.effect.type == "block"
        assert body.when is None
        assert body.match is None
        assert body.group is None

    def test_full_rule(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.BEFORE_TOOL,
            when="variables.get('require_task_before_edit') and not task_claimed",
            match={"tool": "Edit"},
            effect=RuleEffect(
                type="block",
                reason="Claim a task first",
                tools=["Edit", "Write", "NotebookEdit"],
            ),
            group="task-enforcement",
        )
        assert body.event == RuleEvent.BEFORE_TOOL
        assert body.when is not None
        assert body.match == {"tool": "Edit"}
        assert body.effect.reason == "Claim a task first"
        assert body.group == "task-enforcement"

    def test_set_variable_rule(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.AFTER_TOOL,
            when="event.data.get('mcp_tool') == 'claim_task'",
            effect=RuleEffect(type="set_variable", variable="task_claimed", value=True),
            group="task-enforcement",
        )
        assert body.event == RuleEvent.AFTER_TOOL
        assert body.effect.variable == "task_claimed"

    def test_inject_context_rule(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.SESSION_START,
            when="variables.get('session_task')",
            effect=RuleEffect(
                type="inject_context",
                template="You are working on task {{ variables.session_task }}.",
            ),
            group="auto-task",
        )
        assert body.event == RuleEvent.SESSION_START
        assert body.effect.template is not None

    def test_mcp_call_rule(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.SESSION_START,
            effect=RuleEffect(
                type="mcp_call",
                server="gobby-memory",
                tool="sync_import",
            ),
            group="memory-lifecycle",
        )
        assert body.event == RuleEvent.SESSION_START
        assert body.effect.server == "gobby-memory"

    def test_stop_event_rule(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.STOP,
            when="variables.get('_tool_block_pending')",
            effect=RuleEffect(
                type="block",
                reason="A tool was blocked - follow the instructions.",
            ),
            group="stop-gates",
        )
        assert body.event == RuleEvent.STOP

    def test_pre_compact_event_rule(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.PRE_COMPACT,
            effect=RuleEffect(
                type="mcp_call",
                server="gobby-sessions",
                tool="extract_handoff_context",
            ),
            group="context-handoff",
        )
        assert body.event == RuleEvent.PRE_COMPACT

    def test_event_from_string(self) -> None:
        """RuleDefinitionBody should accept event as string."""
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event="before_tool",
            effect=RuleEffect(type="block", reason="test"),
        )
        assert body.event == RuleEvent.BEFORE_TOOL

    def test_serialization_roundtrip(self) -> None:
        """RuleDefinitionBody should serialize to/from JSON (for definition_json storage)."""
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.BEFORE_TOOL,
            when="not task_claimed",
            match={"tool": "Edit"},
            effect=RuleEffect(
                type="block",
                reason="Claim a task",
                tools=["Edit", "Write"],
            ),
            group="task-enforcement",
        )

        # Serialize to dict/JSON
        data = body.model_dump()
        json_str = json.dumps(data)

        # Deserialize back
        restored = RuleDefinitionBody.model_validate_json(json_str)

        assert restored.event == body.event
        assert restored.when == body.when
        assert restored.match == body.match
        assert restored.effect.type == body.effect.type
        assert restored.effect.reason == body.effect.reason
        assert restored.effect.tools == body.effect.tools
        assert restored.group == body.group

    def test_model_dump_mode_json(self) -> None:
        """model_dump(mode='json') should produce JSON-serializable output."""
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect, RuleEvent

        body = RuleDefinitionBody(
            event=RuleEvent.STOP,
            effect=RuleEffect(type="set_variable", variable="stop_attempts", value=0),
        )
        data = body.model_dump(mode="json")

        # Event should serialize as string value
        assert data["event"] == "stop"
        assert data["effect"]["type"] == "set_variable"
        assert data["effect"]["variable"] == "stop_attempts"
        assert data["effect"]["value"] == 0

    def test_required_fields(self) -> None:
        """event and effect are required."""
        from gobby.workflows.definitions import RuleDefinitionBody

        with pytest.raises(ValidationError):
            RuleDefinitionBody()

    def test_event_required(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEffect

        with pytest.raises(ValidationError):
            RuleDefinitionBody(effect=RuleEffect(type="block"))

    def test_effect_required(self) -> None:
        from gobby.workflows.definitions import RuleDefinitionBody, RuleEvent

        with pytest.raises(ValidationError):
            RuleDefinitionBody(event=RuleEvent.BEFORE_TOOL)
