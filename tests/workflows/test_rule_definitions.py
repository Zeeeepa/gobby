"""Tests for RuleDefinition model and YAML fields in definitions.py."""

from __future__ import annotations

import pytest
import yaml

from gobby.workflows.definitions import (
    RuleDefinition,
    WorkflowDefinition,
    WorkflowStep,
)

pytestmark = pytest.mark.unit


class TestRuleDefinition:
    def test_create_with_tools(self) -> None:
        rule = RuleDefinition(
            tools=["Edit", "Write"],
            reason="Claim a task first",
            when="not task_claimed and not plan_mode",
            action="block",
        )
        assert rule.tools == ["Edit", "Write"]
        assert rule.action == "block"
        assert rule.reason == "Claim a task first"
        assert rule.when == "not task_claimed and not plan_mode"

    def test_create_with_mcp_tools(self) -> None:
        rule = RuleDefinition(
            mcp_tools=["gobby-tasks:close_task"],
            reason="Commit first",
            action="block",
        )
        assert rule.mcp_tools == ["gobby-tasks:close_task"]
        assert rule.tools == []

    def test_create_with_command_pattern(self) -> None:
        rule = RuleDefinition(
            tools=["Bash"],
            command_pattern=r"git\s+push",
            reason="No pushing",
            action="block",
        )
        assert rule.command_pattern == r"git\s+push"

    def test_create_with_command_not_pattern(self) -> None:
        rule = RuleDefinition(
            tools=["Bash"],
            command_not_pattern=r"^uv\s+run",
            reason="Only uv run commands",
            action="block",
        )
        assert rule.command_not_pattern == r"^uv\s+run"

    def test_defaults(self) -> None:
        rule = RuleDefinition(reason="test", action="block")
        assert rule.tools == []
        assert rule.mcp_tools == []
        assert rule.when is None
        assert rule.command_pattern is None
        assert rule.command_not_pattern is None

    def test_all_actions(self) -> None:
        for action in ("block", "allow", "warn"):
            rule = RuleDefinition(reason="test", action=action)
            assert rule.action == action

    def test_to_block_rule_dict(self) -> None:
        """RuleDefinition should convert to block_tools rule dict format."""
        rule = RuleDefinition(
            tools=["Edit", "Write"],
            when="not task_claimed",
            reason="Claim a task first",
            action="block",
        )
        d = rule.to_block_rule()
        assert d["tools"] == ["Edit", "Write"]
        assert d["when"] == "not task_claimed"
        assert d["reason"] == "Claim a task first"

    def test_to_block_rule_dict_mcp(self) -> None:
        rule = RuleDefinition(
            mcp_tools=["gobby-tasks:close_task"],
            reason="Commit first",
            action="block",
        )
        d = rule.to_block_rule()
        assert d["mcp_tools"] == ["gobby-tasks:close_task"]
        assert "tools" not in d


class TestWorkflowDefinitionRuleFields:
    def test_rule_definitions_field(self) -> None:
        defn = WorkflowDefinition(
            name="test",
            rule_definitions={
                "require_task": RuleDefinition(
                    tools=["Edit", "Write"],
                    when="not task_claimed",
                    reason="Claim a task first",
                    action="block",
                ),
            },
        )
        assert "require_task" in defn.rule_definitions
        assert defn.rule_definitions["require_task"].action == "block"

    def test_imports_field(self) -> None:
        defn = WorkflowDefinition(
            name="test",
            imports=["worker-safety", "common-rules"],
        )
        assert defn.imports == ["worker-safety", "common-rules"]

    def test_defaults_empty(self) -> None:
        defn = WorkflowDefinition(name="test")
        assert defn.rule_definitions == {}
        assert defn.imports == []


class TestWorkflowStepCheckRules:
    def test_check_rules_field(self) -> None:
        step = WorkflowStep(
            name="work",
            check_rules=["require_task", "no_push"],
        )
        assert step.check_rules == ["require_task", "no_push"]

    def test_defaults_empty(self) -> None:
        step = WorkflowStep(name="work")
        assert step.check_rules == []


class TestYamlRoundTrip:
    def test_workflow_with_rule_definitions_parses(self) -> None:
        """Test that a YAML workflow with rule_definitions + check_rules parses."""
        yaml_content = """
name: test-workflow
type: step
rule_definitions:
  require_task:
    tools: [Edit, Write, NotebookEdit]
    when: "not task_claimed and not plan_mode"
    reason: "Claim a task before editing files."
    action: block
  no_push:
    tools: [Bash]
    command_pattern: "git\\\\s+push"
    reason: "No pushing allowed."
    action: block
imports:
  - worker-safety
steps:
  - name: work
    description: Do the work
    check_rules: [require_task, no_push]
"""
        data = yaml.safe_load(yaml_content)
        defn = WorkflowDefinition(**data)

        assert len(defn.rule_definitions) == 2
        assert defn.rule_definitions["require_task"].tools == ["Edit", "Write", "NotebookEdit"]
        assert defn.rule_definitions["no_push"].command_pattern == "git\\s+push"
        assert defn.imports == ["worker-safety"]
        assert defn.steps[0].check_rules == ["require_task", "no_push"]
