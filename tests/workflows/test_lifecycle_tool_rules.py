"""Tests for tool_rules field on WorkflowDefinition."""

from __future__ import annotations

import pytest

from gobby.workflows.definitions import WorkflowDefinition

pytestmark = pytest.mark.unit


class TestToolRulesField:
    def test_default_empty(self) -> None:
        """WorkflowDefinition.tool_rules defaults to empty list."""
        defn = WorkflowDefinition(name="test", type="lifecycle")
        assert defn.tool_rules == []

    def test_accepts_rules_list(self) -> None:
        """WorkflowDefinition accepts a list of rule dicts."""
        rules = [
            {"tools": ["Edit", "Write"], "reason": "No editing allowed"},
            {"mcp_tools": ["gobby-tasks:close_task"], "reason": "No closing"},
        ]
        defn = WorkflowDefinition(name="test", type="lifecycle", tool_rules=rules)
        assert len(defn.tool_rules) == 2
        assert defn.tool_rules[0]["tools"] == ["Edit", "Write"]
        assert defn.tool_rules[1]["mcp_tools"] == ["gobby-tasks:close_task"]

    def test_with_when_condition(self) -> None:
        """tool_rules entries can include when conditions."""
        rules = [
            {
                "tools": ["Edit"],
                "when": "not task_claimed",
                "reason": "Claim a task first",
            }
        ]
        defn = WorkflowDefinition(name="test", type="lifecycle", tool_rules=rules)
        assert defn.tool_rules[0]["when"] == "not task_claimed"
