"""Tests for developer.yaml workflow structure.

Verifies: workflow loads without error, expected steps exist,
rule_definitions are present, check_rules reference valid names,
imports resolve correctly.
"""

from __future__ import annotations

import pytest

from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit


EXPECTED_STEPS = [
    "claim_task",
    "red",
    "green",
    "blue",
    "reflect",
    "commit",
    "report_to_parent",
    "shutdown",
    "complete",
]


# =============================================================================
# Basic structure
# =============================================================================


class TestDeveloperWorkflowStructure:
    @pytest.mark.asyncio
    async def test_loads_without_error(self, db_loader: WorkflowLoader) -> None:
        """developer.yaml should load successfully."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        assert defn.name == "developer"
        assert defn.type == "step"

    @pytest.mark.asyncio
    async def test_expected_steps_exist(self, db_loader: WorkflowLoader) -> None:
        """All expected TDD steps should be present."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        step_names = [s.name for s in defn.steps]
        for expected in EXPECTED_STEPS:
            assert expected in step_names, f"Missing step: {expected}"

    @pytest.mark.asyncio
    async def test_step_count(self, db_loader: WorkflowLoader) -> None:
        """Workflow should have exactly the expected number of steps."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        assert len(defn.steps) == len(EXPECTED_STEPS)


# =============================================================================
# Named rules (after refactoring)
# =============================================================================


class TestDeveloperWorkflowNamedRules:
    @pytest.mark.asyncio
    async def test_imports_worker_safety(self, db_loader: WorkflowLoader) -> None:
        """Workflow should import worker-safety rules."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        # Imported rules should be merged into rule_definitions
        assert "no_push" in defn.rule_definitions

    @pytest.mark.asyncio
    async def test_rule_definitions_present(self, db_loader: WorkflowLoader) -> None:
        """Workflow-level rule_definitions should include MCP blocking rules."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        assert "no_agent_spawn" in defn.rule_definitions
        assert "no_task_management" in defn.rule_definitions

    @pytest.mark.asyncio
    async def test_tdd_steps_have_check_rules(self, db_loader: WorkflowLoader) -> None:
        """TDD steps (red, green, blue) should use check_rules for enforcement."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        for step_name in ["red", "green", "blue"]:
            step = defn.get_step(step_name)
            assert step is not None, f"Missing step: {step_name}"
            assert len(step.check_rules) > 0, f"Step {step_name} has no check_rules"
            # Should reference the shared rules
            assert "no_push" in step.check_rules, f"Step {step_name} missing no_push"
            assert "no_agent_spawn" in step.check_rules, f"Step {step_name} missing no_agent_spawn"
            assert "no_task_management" in step.check_rules, (
                f"Step {step_name} missing no_task_management"
            )

    @pytest.mark.asyncio
    async def test_commit_step_has_no_push(self, db_loader: WorkflowLoader) -> None:
        """Commit step should reference no_push rule."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        step = defn.get_step("commit")
        assert step is not None
        assert "no_push" in step.check_rules

    @pytest.mark.asyncio
    async def test_check_rules_reference_valid_names(self, db_loader: WorkflowLoader) -> None:
        """All check_rules references should resolve to known rule_definitions."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        available_rules = set(defn.rule_definitions.keys())
        for step in defn.steps:
            for rule_name in step.check_rules:
                assert rule_name in available_rules, (
                    f"Step '{step.name}' references unknown rule '{rule_name}'. "
                    f"Available: {available_rules}"
                )

    @pytest.mark.asyncio
    async def test_no_duplicate_blocked_mcp_tools(self, db_loader: WorkflowLoader) -> None:
        """TDD steps should not have blocked_mcp_tools (migrated to check_rules)."""
        defn = await db_loader.load_workflow("developer")
        assert defn is not None
        for step_name in ["red", "green", "blue"]:
            step = defn.get_step(step_name)
            assert step is not None
            assert len(step.blocked_mcp_tools) == 0, (
                f"Step '{step_name}' still has blocked_mcp_tools. "
                f"These should be migrated to check_rules."
            )
